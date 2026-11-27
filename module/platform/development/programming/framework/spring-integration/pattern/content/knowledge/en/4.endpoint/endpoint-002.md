# Event-Driven Consumer and Polling Consumer

## 1. Problem to Solve

In a Spring Integration **message flow**, a producer creates or sends messages into a **MessageChannel**, while a receiving endpoint pulls or receives messages to execute an action: business processing, filtering, transformation, routing, data persistence, or forwarding to an external system. The two ways to trigger a message-consuming endpoint are **event-driven consumer** and **polling consumer**.

They address the same question: *When and how does a handler receive a message from a channel?* However, they have different execution mechanisms:

- **Event-driven consumer** subscribes to receive messages from a channel that supports subscription. When a message is sent, the channel invokes the appropriate subscriber.
- **Polling consumer** actively pulls messages from a channel that supports on-demand retrieval, based on a schedule managed by a **poller**.

In the **SPRING_INTEGRATION_PATTERN** module, these two consumption modes are the foundation for practicing **Enterprise Integration Patterns (EIP)** with **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel, and correlation**. Choosing the right consumer affects latency, throughput, error handling, ordering, queue capacity, and scalability.

**Expected outcome:** after this lesson, you will be able to distinguish between the two consumer types, choose the right channel, create endpoints using annotations or Java DSL, tune a poller, test message paths, and identify what guarantees actually hold when moving to asynchronous processing.

## 2. Where the Consumer Sits in Spring Integration Architecture

A simple flow looks like this:

~~~mermaid
flowchart LR
    A[Producer or Gateway] --> B[MessageChannel]
    B --> C[Consumer endpoint]
    C --> D[MessageHandler]
    D --> E[Business system / next channel]
~~~

In the diagram, **MessageChannel** is the message-exchange boundary; **consumer endpoint** decides how reception is triggered; **MessageHandler** performs the work once the message has been delivered. Do not equate the consumer with the handler: the same handler can be wired to a channel under different consumption mechanisms.

Two channel interfaces are directly involved:

| Interface | Primary Operation | Typical Consumer |
|---|---|---|
| `SubscribableChannel` | Allows a handler to **subscribe/unsubscribe** to receive messages dispatched by the channel | **Event-driven consumer** |
| `PollableChannel` | Allows a consumer to call `receive()` or `receive(timeout)` to pull messages | **Polling consumer** |

Some familiar implementations:

- `DirectChannel`: a subscribable channel that typically invokes the handler directly on the sender's thread.
- `PublishSubscribeChannel`: a channel that broadcasts to subscribers according to configuration; not a queue for each consumer to call `receive()`.
- `ExecutorChannel`: a subscribable channel that hands off work via an `Executor`; therefore processing can happen on another thread.
- `QueueChannel`: a pollable channel supporting `receive()`; messages are held in a queue until a consumer receives them, within configured bounds.
- `PriorityChannel`: a form of pollable channel where a priority policy can affect the order in which messages are retrieved.

Key point: **the consumer type is determined by the channel interface it receives from**, not solely by whether a user invokes the endpoint over HTTP or whether the message originates from an external system.

## 3. Event-Driven Consumer: Receiving When the Channel Dispatches

An event-driven consumer is typically created when an endpoint's `inputChannel` is a `SubscribableChannel`. At application startup, the endpoint registers a `MessageHandler` with the channel. When a producer sends a message to the channel, the channel dispatches the message to a handler according to that channel's mechanics.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as DirectChannel
    participant E as EventDrivenConsumer
    participant H as Handler
    P->>C: send(Message)
    C->>E: dispatch to subscriber
    E->>H: handleMessage(Message)
    H-->>E: completes or throws exception
    E-->>C: returns control
    C-->>P: send completes or errors
~~~

With `DirectChannel`, the path is typically **synchronous**: the handler runs on the thread that called `send()`; slow processing makes the sender wait longer. If the handler throws an exception, the error can propagate back through the send call to the Gateway/caller. Here, event-driven **does not mean background execution**.

By contrast, `ExecutorChannel` also belongs to the subscribable channel group, but it can delegate processing to a thread pool and change when exceptions surface. Therefore, separate two questions:

1. **Who triggers the consumer?** Does the channel actively dispatch, or does a poller call `receive()`?
2. **Where does the handler execute?** On the sender's thread, an executor thread, or a scheduler thread?

Event-driven consumers fit short in-process work, low-latency flows, or EIP pipelines with sequential steps like **Filter → Transformer → Router** that do not yet require a queue.

### Illustration with Filter and Router

~~~mermaid
flowchart LR
    G[Gateway] --> D[DirectChannel]
    D --> F{Filter valid?}
    F -->|Yes| T[Transformer]
    F -->|No| X[Rejected channel]
    T --> R{Router by region}
    R -->|VN| VN[Consumer VN]
    R -->|Other| OS[Other consumer]
~~~

Each endpoint in the pipeline can use a subscribable input channel. If the entire chain uses `DirectChannel`, an error or slow step in one handler directly affects the producer. When you need to decouple the speeds of stages, consider an asynchronous boundary or a queued channel, while also evaluating load limits and data durability.

## 4. Polling Consumer: Receiving Messages on a Poller Schedule

A **Polling consumer** receives messages from a `PollableChannel`. Instead of subscribing, a scheduler (*poller*) triggers channel checks and then invokes the handler if a message is retrieved.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as QueueChannel
    participant T as Poller / Scheduler
    participant E as PollingConsumer
    participant H as Handler
    P->>Q: send(Message A)
    Note over Q: Message A is waiting
    T->>E: trigger on schedule
    E->>Q: receive(timeout)
    Q-->>E: Message A
    E->>H: handleMessage(A)
    H-->>E: completes or errors
    Note over T,E: Next poll depends on trigger configuration
~~~

A single poll can process **multiple messages**, depending on the `maxMessagesPerPoll` configuration. If the queue is empty, a poll cycle may process no messages. The poller is a **scheduling/consumption coordinator**, not a durable broker.

Components to distinguish:

| Component | Role |
|---|---|
| `QueueChannel` | Temporarily buffers messages waiting to be fetched via `receive()` |
| `PollingConsumer` | Endpoint that pulls messages from a channel and invokes `MessageHandler` |
| `PollerMetadata` | Configures schedule, max messages per poll, and coordination options |
| `TaskScheduler` / trigger | Determines when the next poll is triggered |
| `MessageStore` (if configured) | Determines how messages are stored; may be in-memory or durable depending on implementation |

Polling consumers are useful when data arrives faster than it can be processed, when you want bounded batch-like consumption, or when work fits a queue-and-schedule model. However, **adding a QueueChannel does not automatically create durability**: the default in-memory queue can lose data when the application stops.

## 5. Comparison Table of the Two Mechanisms

| Criterion | Event-Driven Consumer | Polling Consumer |
|---|---|---|
| Input channel | `SubscribableChannel` | `PollableChannel` |
| Reception mechanism | Channel dispatches to subscriber | Consumer calls `receive()` via poller |
| Trigger | A message is sent and the channel dispatches it | Poll trigger/schedule fires |
| Channel examples | `DirectChannel`, `ExecutorChannel`, `PublishSubscribeChannel` | `QueueChannel`, `PriorityChannel` |
| Latency | Usually low if handler is ready, depends on channel type | Depends on schedule, load, wait time, and backlog |
| Producer/consumer isolation | Low with `DirectChannel`; can be higher with executor | Has a buffer queue, though capacity must still be controlled |
| Execution thread | Sender's thread or executor depending on channel | Usually poller scheduler/executor thread |
| Ordering | Depends on channel type and concurrency | Depends on queue, poller, and concurrency |
| Errors | Can propagate back to sender in synchronous flows | Occurs on poller thread; requires explicit error/recovery mechanism |
| Retry/durability | Not built in | Not built in |
| Best suited for | Short flows, immediate processing, internal EIP branches | Buffering, throttling work, paced processing, and small batches |

**Neither option is inherently faster or more reliable in every situation.** For instance, using `ExecutorChannel` introduces asynchrony while remaining event-driven, whereas a poller with a short interval and a consistently full queue can still achieve high throughput.

## 6. Spring Integration Example: Two Endpoints Sharing a Business Payload

The following code illustrates **one consumer receiving immediately via `DirectChannel`** and **one consumer pulling messages from `QueueChannel` at a fixed interval**. It works with Spring Boot configured with Spring Integration; standard imports are omitted to focus on the two consumption styles.

~~~java
record OrderPlaced(String orderId, String region) {}

@Configuration
@EnableIntegration
class ConsumerChannels {

    @Bean(name = "orders.immediate")
    MessageChannel immediateChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.buffered")
    PollableChannel bufferedChannel() {
        return new QueueChannel(100); // Limit to 100 queued messages.
    }

    @Bean
    OrderConsumers orderConsumers() {
        return new OrderConsumers();
    }
}

class OrderConsumers {

    @ServiceActivator(inputChannel = "orders.immediate")
    public void consumeImmediately(OrderPlaced order) {
        System.out.println("EVENT: " + order.orderId());
    }

    @ServiceActivator(
        inputChannel = "orders.buffered",
        poller = @Poller(fixedDelay = "1000", maxMessagesPerPoll = "5")
    )
    public void consumeFromQueue(OrderPlaced order) {
        System.out.println("POLL: " + order.orderId());
    }
}
~~~

Both methods handle the `OrderPlaced` payload, but their message reception boundaries differ:

- `consumeImmediately()` is called when `orders.immediate` dispatches a message to its subscriber. With `DirectChannel`, it typically runs directly on the sender's thread.
- `consumeFromQueue()` is invoked by a polling endpoint after pulling messages from `orders.buffered`. The poller configures `fixedDelay = "1000"` in **milliseconds**, and each poll attempts to process up to **5 messages**, if available.

Example sending messages from code using the application context:

~~~java
MessageChannel immediate =
    context.getBean("orders.immediate", MessageChannel.class);
MessageChannel buffered =
    context.getBean("orders.buffered", MessageChannel.class);

Message<OrderPlaced> event = MessageBuilder
    .withPayload(new OrderPlaced("ORD-101", "VN"))
    .setHeader("correlationId", "ORD-101")
    .build();

immediate.send(event); // Invokes subscriber via DirectChannel semantics.
buffered.send(event);  // Enqueues for the poller to pull.
~~~

In this example, the same message object is used purely to compare the two paths. In real business logic, do not send the same event down both branches if both produce the same side effect, unless clear idempotency rules are in place.

A successful return from `send()` to `QueueChannel` only indicates the message was **accepted by the channel** at that moment; it does not prove the handler has finished processing or that the message will survive a restart.

### Equivalent Configuration in Java DSL

If you prefer expressing handler wiring with Java DSL, you can declare the two flows below. This is an **alternative** to the two `@ServiceActivator`-annotated methods above: use only one consumer wiring approach per channel in the same example to avoid duplicate processing.

~~~java
@Bean
IntegrationFlow eventConsumerDsl() {
    return IntegrationFlow.from("orders.immediate")
        .handle(message ->
            System.out.println("EVENT: " + message.getPayload()))
        .get();
}

@Bean
IntegrationFlow pollingConsumerDsl() {
    return IntegrationFlow.from("orders.buffered")
        .handle(
            message -> System.out.println("POLL: " + message.getPayload()),
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofSeconds(1))
                    .maxMessagesPerPoll(5)))
        .get();
}
~~~

The two channel beans from the previous example are still used. The first endpoint needs no poller because the channel supports subscription. The second endpoint **must have a poller** to pull messages from the `PollableChannel`; endpoint configuration defines the polling cadence and batch size.

## 7. Poller Configuration: Frequency, Limits, and Overload Risk

A poller must be configured according to ingress rate, processing rate, queue size, and latency requirements. Common parameters:

| Parameter | Meaning | When to Tune |
|---|---|---|
| `fixedDelay` | Waits a period after the previous poll finishes before scheduling the next | When you want to avoid overlapping or tightly packed cycles under slow processing |
| `fixedRate` | Schedules on a periodic time cadence | When a fairly steady trigger cadence is needed; check thread limits |
| `maxMessagesPerPoll` | Limits the maximum number of message fetches/processes per cycle | Limit how much work a single poll cycle can occupy |
| `receiveTimeout` | Wait time when receiving from a channel, if applicable | Avoid holding a poller thread too long when the queue is empty |
| `taskExecutor` | Executor used per poller configuration | Throttle concurrency when multiple messages need processing |
| `errorChannel` / error handler | Route receiving errors from polling work per configuration | Categorize errors, alert, or route to recovery workflows |

**Example of interpreting poll cadence:** configuring `fixedDelay = 1000 ms`, `maxMessagesPerPoll = 5` does not mean the system always processes exactly **5 messages/second**. If handlers are slow, the queue is empty, or the scheduler is busy, the actual rate differs substantially. The poller must finish one cycle before the `fixedDelay` trigger schedules the next.

Suppose a handler takes an average of **200 ms/message**. With one polling thread and `maxMessagesPerPoll = 5`, five messages can take about one second of processing, excluding I/O and inter-cycle wait time. If producers send 20 messages/second while consumers finish fewer than 5 messages/second, the queue will build up regardless of fixed delay.

Avoid configuring a poller to drain unlimited messages in a single cycle when the queue is frequently full; an overly long cycle can starve other tasks sharing the scheduler. A positive limit, small enough to observe and tune, is a sensible starting point.

### Distinguishing `fixedDelay` and `fixedRate`

~~~text
fixedDelay = 1s
[poll + processing] --- wait 1s --- [poll + processing] --- wait 1s --- ...

fixedRate = 1s
|-- tick 1 --|-- tick 2 --|-- tick 3 --|...
    Actual execution timing still depends on processing duration and scheduler.
~~~

`fixedRate` does not guarantee that slow handlers will execute concurrently or that every trigger will fire to the exact millisecond; scheduler constraints and executor configuration determine parallel execution. Measure with real metrics rather than inferring behavior from configuration values alone.

## 8. Polling Consumer Is Not the Same as a Polling Inbound Adapter

This is a frequent point of confusion in Spring Integration.

A **Polling consumer** receives messages **from a `PollableChannel`** and passes them to a handler:

~~~text
Producer → QueueChannel → PollingConsumer → Service Activator
~~~

A **Source polling inbound channel adapter** actively polls a **MessageSource** such as a file directory, JDBC, or a pull-only API system, and then **emits messages into a channel**. This type of endpoint acts as a source feeding data into the flow:

~~~text
File/JDBC/pull API source → MessageSource
                               ↑
                            Poller
                               ↓
                      Inbound channel adapter
                               ↓
                        MessageChannel
                               ↓
                        Consumer endpoint
~~~

For example: using a File inbound adapter to scan a directory every 5 seconds and then emit files into a `DirectChannel` with an immediate consumer. The overall flow has *polling behavior at the input*, yet the `DirectChannel` consumer is still an **event-driven consumer**.

A message broker may also have an internal fetch/poll API in its client library. That alone does not mean the **Spring Integration** consumer endpoint is necessarily a `PollingConsumer`: check what channel type the adapter emits to and how the endpoint is wired.

## 9. Threading, Ordering, and Backpressure Models

In practice, whether execution preserves order depends on both the channel and concurrency level:

1. **DirectChannel + synchronous handler**: the producer waits for the handler; call order on a single thread is easy to follow, though multiple producer threads can still send concurrently.
2. **ExecutorChannel**: the producer hands off work via an executor; completion order may differ from send order.
3. **QueueChannel + single sequential polling consumer**: typically pulls in FIFO order from the default queue, though final side-effect order may differ if the handler spawns parallel work itself.
4. **PriorityChannel**: priority can cause later messages to be pulled earlier.
5. **Multiple polling consumers / workers**: can increase throughput but also increase the risk of interleaved execution and out-of-order completion.

If orders must be processed sequentially per `orderId`, do not rely solely on a shared queue. Consider key-based partitioning, per-key concurrency limits, or a business-level serialization mechanism. With **Splitter/Aggregator**, preserve and verify `correlationId`, `sequenceNumber`, and `sequenceSize` as messages split and reconverge.

**Backpressure** is the system's ability to handle producers running faster than consumers:

| Mechanism | Effect | Limitation to Understand |
|---|---|---|
| Synchronous handler via `DirectChannel` | Producer rate is directly throttled by handler duration | Can increase latency and tie up caller threads |
| Bounded-capacity queue | Holds messages in a finite backlog | When the queue is full, the sender must handle rejection/blocking |
| Poller with bounded concurrency | Limits how many tasks are pulled or running | Does not automatically throttle upstream producer ingress rate |
| Durable broker | Reduces dependence on a single process lifecycle | Requires configuring ack, storage, retry, DLQ, and capacity separately |

Do not place an unbounded queue in a high-ingress system without sizing memory, wait times, and alerting. With `QueueChannel(100)`, explicitly specify how the producer handles failed sends or a full queue, rather than assuming every `send()` succeeds.

## 10. Error Channel, Retry, and Behavior When a Handler Fails

Consumer endpoints typically invoke a `MessageHandler`. However, **where errors are reported** depends on the execution boundary:

| Scenario | Where Error Surfaces | What Must Be Designed |
|---|---|---|
| `DirectChannel` invokes handler that throws exception | Can propagate back on sender/Gateway thread | Caller catches error and decides retry/response |
| `ExecutorChannel` processes on another thread | No longer on producer's call stack | Executor/flow error handling, observability, and retry |
| Poller pulls from `QueueChannel`, handler throws exception | Error occurs inside polling task | Error channel/error handler, recovery, and policy for the pulled message |
| Consumer receives from a broker | Error involves both adapter and broker | Ack/nack, redelivery, retry/DLQ per configuration |

**Especially with `QueueChannel`:** once `receive()` has pulled a message out of an in-memory queue, a handler throwing an exception **does not put the message back into the queue by default**. If tasks must not be lost on errors or restarts, design durable storage, appropriate transactions/recovery, or use a broker with explicit receive and acknowledgement policies.

Bounded retry can be applied to an endpoint via advice where appropriate, combined with backoff and retryable-exception filtering. However, retrying an operation that already produced side effects (charging money, creating an invoice) can cause duplicate data. Use an idempotency key and define when a message is considered completed.

If a message is permanently malformed, do not retry indefinitely. Route it to a rejection channel, dead-letter queue, or error-analysis workflow. With **Filter**, the discard channel handles unmet conditions; with **exceptions**, the error path is a separate mechanism and must be configured accordingly.

## 11. When Should You Choose Each Approach?

Some typical scenarios:

| Scenario | Recommendation | Reason |
|---|---|---|
| Gateway calls a Filter → Transformer → Router chain in JVM | `DirectChannel` and event-driven | Fewer components, easy to trace, and low latency |
| Need to offload handler to a thread pool; producer does not wait synchronously | `ExecutorChannel` and event-driven | Decouples threads while keeping subscription |
| Many orders arrive rapidly, inventory processing is slower, and bounded buffering is wanted | `QueueChannel` + polling consumer | Throttles message consumption and exposes backlog |
| Scanning a directory to ingest new files | Polling inbound adapter + appropriate channel | Polls external source; downstream consumer can be event-driven |
| Need to send data across two independent microservices and recover after restarts | Adapter/broker configured with persistence, ack, and retry | Crosses process boundaries; plain in-memory channels are not enough |
| Need an immediate response for the caller when business processing completes | Synchronous flow with clear reply/error design | Easy to correlate response with call; must manage timeouts |

**Quick selection workflow:** determine response requirements (synchronous or asynchronous), acceptable latency, ingress/egress rates, memory limits, ordering, error policy, and recovery requirements. Only then choose the channel and consumer type. Do not choose polling just because a task is “heavy,” or event-driven just because the producer emits an “event.”

## 12. Testing Consumers by Type

To verify an endpoint, you need to observe which handler receives messages, when, and whether any errors or backlogs occur. Spring Integration supports flow testing and endpoint mocking; for exercises, you can also use handlers that record messages into thread-safe collections and synchronize results with a latch.

| Test | Setup | Expected Result |
|---|---|---|
| Event-driven with `DirectChannel` | Send a valid `OrderPlaced` | Handler is called before the synchronous send returns |
| Event-driven throwing an error | Handler intentionally throws an exception | Sender observes the error on the configured call path |
| Poller with empty queue | Do not send messages to `QueueChannel` | No spurious business processing; endpoint remains healthy |
| Poller with backlog | Send more than `maxMessagesPerPoll` messages | Multiple poll cycles needed; all valid messages are eventually processed |
| Full queue | Small capacity, producer sends beyond capacity | Send/wait/reject outcome matches timeout and producer policy |
| Slow handler | Add controlled delay | Backlog and throughput are measured without misinterpreting `fixedDelay` |
| Polling handler throws error | Simulate failure during one receive | Error is recorded; verify whether the message is retried or lost |
| High concurrency | Increase worker/thread count | Detect changes in completion order and shared-state issues |
| Correlation | Two orders split/aggregated interleaved | No result from one order leaks into another |

For polling consumers, avoid testing by calling `Thread.sleep()` for a fixed duration and assuming all messages were processed. Use completion conditions with bounded timeouts, recording start/end timestamps, queue depth, and handler invocation counts. When deterministic behavior is needed, control the scheduler or trigger polls in an appropriate test setup.

When using `ExecutorChannel`, verify side effects and exceptions on executor threads. When using a broker, add integration tests for worker shutdown, restarts, redelivery, retries, and idempotency.

## 13. Observability and Operations

Choosing a consumer mechanism is not enough to operate a flow reliably. Monitor:

- **Ingress rate**: messages entering each channel per unit of time.
- **Processing rate and duration**: completed message count, average latency, and p95/p99 at the handler.
- **Queue depth / backlog age**: how many messages are waiting and how long the oldest message has waited.
- **Poll activity**: polls that fetched messages, empty polls, messages processed per poll.
- **Failures, retries, and DLQ**: error rate, error types, retry counts, and messages requiring manual handling.
- **Correlation/tracing**: `messageId`, `correlationId`, `orderId`, and trace context needed to follow requests through Gateway, Router, Splitter, and Aggregator.

Micrometer and Spring observability mechanisms can capture metrics/tracing when properly configured. Use consistent channel/endpoint names, minimize logging of sensitive payloads, and set alerts on backlog, age, errors, or latency. For polling consumers, a steadily growing queue metric signals that producers exceed processing capacity or consumers are failing.

In a distributed system, a message may be redelivered after a failure or lost response; do not rely solely on a newly generated `messageId` for business deduplication. Use a stable business key, such as `eventId`/idempotency key, and safe processing-state persistence.

## 14. Hands-on Lab: Converting an Order Processing Flow from Push to Poll

Build a prototype application with the payload:

~~~java
record OrderPlaced(
    String eventId,
    String orderId,
    String region,
    int itemCount
) {}
~~~

**Phase A — Event-driven:** create a Gateway sending `OrderPlaced` to a `DirectChannel`; a Filter rejecting `itemCount <= 0`; a Transformer normalizing `region`; a Router splitting `VN` and `OTHER`; and a Service Activator recording the order and correlation ID. Measure single-send latency and test a handler throwing an exception. Document whether the error propagates back to the Gateway.

**Phase B — Polling:** add a `QueueChannel` with capacity 100 and a polling consumer with `fixedDelay = 1000 ms`, `maxMessagesPerPoll = 5`. Emit 200 simulated messages while intentionally slowing down the handler. Observe when the queue fills up, how many messages the producer sends successfully, how long it takes to drain the backlog, and behavior when the handler throws an exception.

**Phase C — Recoverability:** keep test data and business state consistent by selecting an appropriate message store/broker, simulating a mid-flight restart, and resending the same `eventId`. Verify idempotency and correlation; record which messages were persisted, processed, queued, or failed.

**Completion criteria:**

1. Explain why `DirectChannel` creates an event-driven consumer and `QueueChannel` creates a polling consumer on the two configured endpoints.
2. Demonstrate that event-driven is not asynchronous by default and polling is not durable by default.
3. Provide throughput, queue depth, latency, and backlog drain time measurements for at least two poller configurations.
4. Include tests for Filter/Router, correlation, and both error-handling paths.
5. Describe the handling plan for queue full, handler failures, message redelivery, and worker restarts.

## 15. Design Mistakes to Avoid

**Confusing event-driven with asynchronous.** `DirectChannel` dispatches via subscription but normally runs on the sender's thread; switching to `ExecutorChannel` is what changes execution to an executor.

**Confusing a polling consumer with a polled source.** A polling consumer pulls from a `PollableChannel`; an inbound adapter uses a `MessageSource` to fetch external data and emit messages to a channel. Both patterns can appear in the same flow.

**Treating QueueChannel as a durable broker.** An in-memory queue only provides a buffer between producer and consumer. Restart recovery, retries, transactions, and redelivery must be designed separately.

**Increasing concurrency without checking ordering and correlation.** Speed may increase, but related messages may complete out of order. This is especially critical when Splitter and Aggregator rely on sequence headers.

**Assuming maxMessagesPerPoll is a messages-per-second cap.** This parameter controls messages per poll cycle, while actual throughput depends on the handler, trigger, scheduler, and queue state.

**Not measuring backlog and error paths.** A flow may appear to “run normally” even while messages wait for minutes or are lost after a polling handler fails. Metrics, timeouts, and idempotency must accompany endpoint design.

## 16. Summary

An **Event-driven consumer** receives messages via `SubscribableChannel` subscription; a **polling consumer** pulls messages from a `PollableChannel` on a poller schedule. The difference lies in who initiates delivery to the handler, how execution is scheduled, latency, and backlog throttling.

In Spring Integration, start with the message contract and business requirements, pick the corresponding channel/consumer, and then apply **Filter, Transformer, Router, Splitter, Aggregator, Gateway, retry, error channel, and correlation** at the exact points needed. Finally, test all branches, measure throughput/latency/backlog, and verify error handling before scaling a message flow across multiple processes.
