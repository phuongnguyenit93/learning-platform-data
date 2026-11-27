# SourcePollingChannelAdapter and Message Sources

In Spring Integration, many data sources do not proactively push events into the application. The application must periodically poll the source to check whether new data is available. This mechanism is implemented using **SourcePollingChannelAdapter** combined with a **MessageSource**.

MessageSource is responsible for retrieving one message from the source. SourcePollingChannelAdapter is responsible for invoking the source on a schedule, receiving the message, and then sending that message into the flow's channel. The poller determines the retrieval cadence and the maximum number of messages retrieved per cycle.

This is a pull model: the application actively fetches data. It fits database tables that need periodic scanning, file directories, queues with a receive API, stateful sources, or systems that do not support push. Understanding the adapter and source properly helps control latency, system load, transactions, retries, and safe application shutdown.

## 1. Polling source architecture

A source polling flow typically has the following components:

- **Data source**: database, file system, API, queue, or a custom source.
- **MessageSource<T>**: abstraction that fetches data and returns a Message<T> or null when no data is available.
- **SourcePollingChannelAdapter**: endpoint that polls the MessageSource and sends messages to the output channel.
- **Poller**: describes the trigger, per-poll message count limit, and related advice.
- **TaskScheduler**: schedules the next polling execution.
- **Channel and downstream endpoints**: receive and process messages just like other Spring Integration flows.

~~~mermaid
flowchart LR
    A["Database / File / API / Queue"] --> B["MessageSource"]
    B --> C["SourcePollingChannelAdapter"]
    T["Poller + Trigger"] --> C
    S["TaskScheduler"] --> T
    C --> D["Output MessageChannel"]
    D --> E["Handler / Service Activator"]
    E --> F["Next flow"]
    C -. "exception" .-> X["Error handling"]
~~~

MessageSource does not schedule itself. It only defines how to retrieve a single message. The adapter is the component that ties the source to a polling schedule and an output channel.

Distinguish this adapter from an event-driven inbound adapter. With a broker listener or external system callback, the source actively calls the application when an event occurs. With SourcePollingChannelAdapter, the application actively calls receive() on a schedule. These two inbound styles differ in load control, latency, and lifecycle.

## 2. The MessageSource contract

MessageSource<T> is the core abstraction for polling sources. The primary contract is:

~~~java
public interface MessageSource<T> {
    Message<T> receive();
}
~~~

When invoked:

- If data is available, the source returns a Message<T>.
- If no data is currently available, the source returns null.
- If data cannot be retrieved due to an error, the source may throw an exception.

`null` is a normal signal: this poll has no message to send. It is neither an empty message nor necessarily an error. The polling adapter uses this result to know there are no more messages in the current fetch cycle.

The returned message can be constructed directly inside the source using MessageBuilder, or created by an adapter wrapping an API that returns a payload. When the source returns a message, it can set necessary headers such as source identifier, partition, tenant, business timestamp, or metadata for downstream processing.

Example of a simple source:

~~~java
@Component
class PendingOrderSource implements MessageSource<Order> {

    private final OrderRepository repository;

    PendingOrderSource(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Message<Order> receive() {
        Order order = repository.claimNextPendingOrder();

        if (order == null) {
            return null;
        }

        return MessageBuilder.withPayload(order)
                .setHeader("app.orderId", order.id())
                .setHeader("app.source", "pending-orders")
                .build();
    }
}
~~~

The example assumes the repository has an appropriate claimNextPendingOrder() operation to acquire processing ownership of a record. With multiple application instances, selecting and claiming records must be designed atomically in the database or via a lock/lease mechanism. Simply running a SELECT and then updating status in two separate operations can cause two instances to pick up the same order.

A MessageSource should have these characteristics:

- Each receive() call has predictable cost and wait time.
- Returns null only when the source currently has no message.
- Does not silently swallow connection errors or data errors.
- Has clear rules on whether records are already claimed, acknowledged, committed, or will be read again.
- Returns enough metadata to trace source, correlation, and processing status.

## 3. What does SourcePollingChannelAdapter do in a cycle?

Conceptually, a polling cycle proceeds as follows:

1. The scheduler triggers the polling task according to the trigger.
2. The adapter calls MessageSource.receive().
3. If the source returns null, the adapter ends the retrieval cycle.
4. If the source returns a message, the adapter sends the message to the output channel.
5. The poller may continue calling the source within the same cycle until maxMessagesPerPoll is reached or the source has no more messages.
6. When the cycle ends, the scheduler waits for the next trigger.

~~~mermaid
flowchart TD
    A["Poll time reached"] --> B["Call MessageSource.receive()"]
    B --> C{"Message returned?"}
    C -- "No: null" --> G["End cycle"]
    C -- "Yes" --> D["Send to output channel"]
    D --> E{"Reached maxMessagesPerPoll?"}
    E -- "Not yet" --> B
    E -- "Yes" --> G
    G --> H["Wait for next trigger"]
    H --> A
~~~

Note that SourcePollingChannelAdapter does not necessarily call the source only once per scheduler trigger. The number of calls depends on maxMessagesPerPoll and whether the source keeps returning messages.

If maxMessagesPerPoll is a positive integer, it caps the maximum number of messages retrieved in one cycle. A value of -1 is used to keep receiving until the source returns null. Large batches can increase throughput, but also lengthen a single poll cycle, occupy the scheduler thread longer, and increase latency for other tasks if the scheduler is shared.

## 4. Configuring a poller in Java DSL

Java DSL lets you build a flow directly from a MessageSource and configure a poller for the source endpoint.

~~~java
@Bean
IntegrationFlow pendingOrders(
        PendingOrderSource source,
        OrderService orderService) {

    return IntegrationFlow.from(source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(1))
                                    .maxMessagesPerPoll(20)))
            .handle(orderService, "process")
            .get();
}
~~~

In this example:

- source is a MessageSource<Order>.
- fixedDelay(Duration.ofSeconds(1)) sets the delay between polling executions according to configuration.
- maxMessagesPerPoll(20) caps a single cycle at 20 messages.
- handle(...) is the next processing step of the flow.

If the source only has 3 messages, the cycle ends when the source returns null; the adapter does not wait to collect all 20 messages. If the source continuously has data, a single cycle can pull all 20 messages before yielding to the next schedule.

### Using MessageSource as a bean

You can declare the source separately as a bean to separate data retrieval logic from flow definition:

~~~java
@Bean
MessageSource<Order> orderSource(OrderRepository repository) {
    return () -> {
        Order order = repository.claimNextPendingOrder();
        return order == null
                ? null
                : MessageBuilder.withPayload(order).build();
    };
}

@Bean
IntegrationFlow orderPollingFlow(MessageSource<Order> orderSource,
                                 OrderService orderService) {
    return IntegrationFlow.from(orderSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(500)
                                    .maxMessagesPerPoll(10)))
            .handle(orderService, "process")
            .get();
}
~~~

This approach is convenient when you want to unit test the source independently, reuse the source, or swap implementations without changing the flow.

## 5. Using @InboundChannelAdapter

Besides Java DSL, you can use the @InboundChannelAdapter annotation to register a method or bean as an inbound polling source.

~~~java
@Bean
@InboundChannelAdapter(
        channel = "orders.in",
        poller = @Poller(
                fixedDelay = "1000",
                maxMessagesPerPoll = "10"))
public MessageSource<Order> ordersSource(OrderRepository repository) {
    return () -> {
        Order order = repository.claimNextPendingOrder();
        return order == null
                ? null
                : MessageBuilder.withPayload(order).build();
    };
}

@Bean
IntegrationFlow processOrders(OrderService orderService) {
    return IntegrationFlow.from("orders.in")
            .handle(orderService, "process")
            .get();
}
~~~

The annotation creates the inbound adapter infrastructure from the method configuration. The `orders.in` channel is where the adapter sends messages into the flow.

You can use a method returning a payload or returning a Message depending on the declaration style and specific API. When custom headers are needed, returning a Message makes payload and metadata explicit. Avoid creating an extra poller for the same source just because a downstream flow also has polling configuration: @InboundChannelAdapter is already a polling source; subsequent event-driven endpoints receive messages via the channel.

## 6. Choosing a trigger: fixed delay, fixed rate, and cron

A poller needs a trigger so the scheduler knows when to run the next poll.

| Trigger | Meaning | When Suitable |
|---|---|---|
| Fixed delay | Waits a period of time after the previous execution finishes before running again | Source has variable processing times or load piling must be avoided |
| Fixed rate | Schedules on a fixed periodic interval | Steady poll cadence is needed and task runtime is stable |
| Cron | Runs according to a calendar schedule expression | Syncing by business hours, start/end of day, or business schedules |

Fixed delay example:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(2))
~~~

Fixed rate example:

~~~java
Pollers.fixedRate(Duration.ofSeconds(5))
~~~

Cron example:

~~~java
Pollers.cron("0 */5 * * * *")
~~~

Spring's cron syntax typically has six fields, including seconds. Check timezone and DST rules when schedules depend on local time.

Fixed delay is generally easier to control when each poll cycle has unstable processing time. Fixed rate suits a steady cadence, though if a task takes longer than the expected interval, actual firing may slip depending on the scheduler and execution configuration. Cron fits business schedules, but does not by itself resolve cases where a previous execution is still running.

Do not pick an overly short polling interval just to reduce latency. Polling every few milliseconds can produce many empty calls, increase database or API load, and tie up the scheduler. Balance acceptable latency against the cost of each source check.

## 7. maxMessagesPerPoll and batch size

maxMessagesPerPoll is the limit on how many messages the adapter fetches from the source in a single poller trigger.

| Value | Behavior |
|---|---|
| Positive integer, e.g. 10 | Retrieves at most 10 messages in one cycle |
| -1 | Continues retrieving until the source returns null |
| Default value | Depends on poller/version configuration and how the endpoint is created; configure explicitly when batching matters operationally |

Large values can raise throughput by reducing scheduling overhead per message. However, overly large batches can:

- Make a single poll occupy the scheduler thread for a long time.
- Create message bursts to downstream systems.
- Lengthen a single poll cycle's transaction.
- Increase the number of messages sitting in memory or queues.
- Delay other sources sharing the same scheduler.

Small values make cycles yield resources more often, but can increase overhead and lower throughput. Choose batch size based on source speed, average processing time, downstream limits, and latency SLAs.

maxMessagesPerPoll is not the number of parallel processing threads. Setting it to 20 does not mean 20 messages run concurrently. In a synchronous flow, messages may be processed sequentially within the same polling task. Increasing concurrency requires designing a separate execution model.

Do not confuse a poller's receiveTimeout used with PollableChannel with a timeout on MessageSource. The MessageSource.receive() contract takes no timeout parameter; if reading from the source can block, the implementation must configure timeouts on the database, socket, or API client itself. If receive() blocks too long, the polling task and scheduler thread can be held up.

## 8. Scheduler and executor: who does what?

In the polling model, distinct roles must be separated:

- **TaskScheduler** schedules when polling tasks run.
- **Poller** holds the trigger and policies for the polling cycle.
- **MessageSource** retrieves messages from the source.
- **TaskExecutor** can be used at asynchronous execution boundaries or per an endpoint's executor configuration.
- **Channel** determines whether messages are dispatched synchronously, broadcast, buffered, or handed off to an executor.

Do not conflate the scheduler with the executor. The scheduler decides when to run; the executor coordinates executing tasks on a thread pool. In real configurations, one scheduler may be shared across many endpoints. If one source blocks for a long time, it can degrade responsiveness for other pollers if they share a scheduler with limited threads.

You can configure separate schedulers for the application or Integration infrastructure when isolating poller groups with different load profiles. When changing thread pools, measure poll counts, poll duration, latency, and executor queue status.

If parallel message processing is needed, you can route messages through an ExecutorChannel or an asynchronous endpoint configured with an executor. When adding that boundary, however, re-evaluate message ordering, transactions, error handling, and shutdown behavior.

## 9. Common message sources

Spring Integration provides many MessageSource implementations and polling-based adapters.

| Source Type | Example | Characteristics |
|---|---|---|
| Database | JdbcPollingChannelAdapter | Runs periodic queries to fetch records; requires a claim/mark-processed strategy |
| File system | FileReadingMessageSource | Scans directories and emits files; requires filter, locking, and archive management |
| Application method | @InboundChannelAdapter | Calls a method on schedule and wraps results into messages |
| Queue or store | Source reading from a queue with a pull API | Must define ack/delete and redelivery |
| Custom source | Application-written MessageSource<T> | Full control over fetching data and metadata |

### Database source

Database polling typically queries pending records. After fetching records, the system must decide when to mark them as received or processed.

A common design uses states like PENDING, PROCESSING, DONE, FAILED along with claim timestamps and leases. Multiple instances may run pollers concurrently, so queries and claim operations must avoid picking the same record twice. A single transaction can span claiming and processing if all operations share the same transaction manager and execution thread; if the flow goes asynchronous, a new transaction boundary is needed at the consumer.

### File source

File sources typically scan directories and apply filters to avoid reading incomplete or already-processed files. After emitting a file, the application can move it to an archive directory, rename it, or record processing status. The fact that a file was emitted by the source does not automatically mean business processing succeeded; completion and recovery rules are needed if downstream fails.

### Custom source

When writing a custom MessageSource, keep receive() focused on fetching/claiming one message and creating metadata. Avoid embedding an entire long business workflow inside the source. Separating the source from handlers keeps testing, retries, and transaction boundaries clearer.

## 10. Transactions and consistency while polling

A poller can attach transaction advice via adviceChain. This lets a transaction wrap a poll execution or the configured portion of work for the poller.

Java DSL example:

~~~java
@Bean
IntegrationFlow transactionalPolling(
        MessageSource<Order> source,
        OrderService orderService,
        PlatformTransactionManager transactionManager) {

    return IntegrationFlow.from(source,
                    e -> e.poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                            .maxMessagesPerPoll(10)
                            .transactional(transactionManager)))
            .handle(orderService, "process")
            .get();
}
~~~

Exact method names and overloads may vary by Spring Integration version; when using your project's DSL, check the corresponding API. From a design perspective, what matters is that the transaction is attached to the poller and covers the exact operations that must be atomic.

Transactions help when the source reads from a transactional resource, such as a database. If claiming a record and updating processing status reside in the same transaction, rollback can restore state when processing fails.

However, not every source can roll back:

- Reading files from a filesystem does not automatically participate in a database transaction.
- Calling an external API may already have caused side effects even if the database transaction rolls back.
- Messages sent to a broker outside the transaction may not be retracted when the database rolls back.
- If the flow crosses an ExecutorChannel or asynchronous queue, the original thread's transaction does not automatically propagate to the consumer.

For multi-resource systems, consider idempotency, outbox/inbox, post-processing ack, and compensation mechanisms. Do not assume a poller transaction produces exactly-once delivery across the entire integration chain.

## 11. Errors when the source or downstream fails

Errors can arise in multiple places:

- MessageSource.receive() fails to connect to the source or the query errors.
- The source constructs a message, but the data is invalid.
- The output channel rejects the message or runs out of capacity.
- A downstream handler throws an exception.
- Transaction commit fails after the handler has already run.

How to handle them depends on whether the error happens in the source, during message sending, or at a downstream endpoint, and whether the flow is synchronous or asynchronous.

In a synchronous flow over DirectChannel, downstream errors can propagate back to the polling task. Across asynchronous boundaries such as executors or queues, errors may surface on another thread or consumer endpoint; monitor the corresponding consumer's error channel and error handler.

Poller advice can be used to attach retry, transaction, or logging advice. Retries should apply to transient errors, with a bounded attempt count and backoff. Do not retry permanent data errors or configuration errors indefinitely, as that causes the poller to fail continuously.

If the source already marked a record as taken before sending it to the channel, and downstream delivery fails, the record can be lost from the pipeline unless a recovery mechanism exists. If the source only reads without claiming, the same record may be emitted repeatedly on subsequent polls. Therefore, source state and acknowledgment semantics must be clearly defined.

## 12. Acknowledgement, redelivery, and idempotency

MessageSource does not enforce a single universal acknowledgment strategy across all sources. The meaning of receive() depends on the implementation:

- Some sources only read records without altering source state.
- Some sources claim or delete messages immediately upon receipt.
- Some sources only mark completion after a separate operation.
- Some adapters use transactions to receive and commit/roll back against the resource.

Three questions must be answered:

1. When does the source consider a message delivered to the application?
2. When does the source consider a message successfully processed?
3. If the application stops between those two points, is the message redelivered, stuck in a processing state, or lost?

If the source acknowledges before business processing completes, a state persistence and recovery mechanism is required. If the source redelivers when no ack is received, handlers must be idempotent to avoid creating duplicate side effects.

A common design uses a stable business key such as orderId or eventId, stores the processed result, and refuses to execute side effects a second time. Do not use MessageHeaders.id as an idempotency key across redeliveries, because a new message may receive a new ID.

## 13. Lifecycle of SourcePollingChannelAdapter

SourcePollingChannelAdapter is an endpoint whose lifecycle is managed by Spring. In typical configurations, it is initialized alongside the application context, registers its poller, and starts the polling schedule when the endpoint starts.

Lifecycle concepts to know:

- **autoStartup**: whether the endpoint starts automatically when Spring's lifecycle processor starts.
- **phase**: relative order among SmartLifecycle components during start and stop.
- **start()**: begins endpoint operation.
- **stop()**: halts endpoint operation and cancels the registered polling schedule.
- **isRunning()**: indicates whether the endpoint is currently in the running state.

Endpoints can be controlled by bean name or via Integration endpoint management mechanisms. For dynamic flows, IntegrationFlowContext allows registering and destroying flows along with their associated endpoints at runtime.

### autoStartup

If autoStartup is enabled, the endpoint is started by the lifecycle processor alongside the context. If disabled, the application can control start timing manually once source connectivity is ready or business initialization steps have completed.

This is useful when a source may only poll after tenant configuration, credentials, or schemas are ready.

### phase

phase determines start/stop order among SmartLifecycle beans. When multiple endpoints depend on each other, phases can be set so inbound sources start only after downstream components are ready. When stopping, the lifecycle processor acts in reverse order to reduce messages sent to already-stopped endpoints.

Do not assign phases arbitrarily to individual beans. Model real dependencies: channels and consumers must be ready before the source emits messages; during shutdown, the source should stop ingesting more data before downstream components are closed.

## 14. Stopping polling safely

Stopping a polling adapter does not mean all in-flight messages automatically roll back or complete. Distinguish:

- The next scheduled poll is cancelled.
- An in-progress receive() call may already be inside the source.
- Messages being processed synchronously may need time to finish.
- Messages already sent to a queue/executor may still be waiting for a consumer.
- Transactions may be mid-commit or mid-rollback.

A safe shutdown procedure typically follows:

1. Stop accepting new work by stopping the source adapter or an equivalent quiesce mechanism.
2. Wait for in-flight executions to finish within the shutdown timeout.
3. Let downstream consumers finish or drain queues per application policy.
4. Close sources, connections, and dependent resources after endpoints have stopped.
5. Record incomplete messages so they can be retried or recovered after restart.

For custom sources with blocking operations, configure I/O timeouts and ensure stop does not hang indefinitely. Do not rely on thread interruption unless the source implementation supports safe interruption.

## 15. Throughput, latency, and backpressure

Polling is an intake throttling point. Three main factors affect throughput:

- **Poll frequency**: polling more frequently can reduce latency to detect new data, but increases the cost of checking the source.
- **Batch size**: larger maxMessagesPerPoll can lower per-message overhead, but each cycle can take longer and create bursts.
- **Downstream speed**: if handlers are slower than retrieval speed, downstream queues or executors can accumulate messages.

SourcePollingChannelAdapter does not automatically provide end-to-end backpressure like Reactive Streams. Polling can throttle intake via triggers and batching, but when sending to a buffered channel, the source can keep pulling messages faster than consumers can process them. Use bounded queues, timeouts, batch limits, and appropriate stop/load-shedding policies.

### Operational signals

| Signal | Cause to Check | Resolution |
|---|---|---|
| Poller runs frequently with no messages | Trigger too short or sparse source data | Increase delay, use cron, or switch to event-driven if supported by source |
| Polling tasks take too long | Slow source query, blocking I/O, or large batch | Measure receive and send times separately; optimize queries, timeouts, and batches |
| Downstream queue grows | Intake faster than processing rate | Reduce batch/frequency, scale consumers safely, or bound the queue |
| Same record processed multiple times | Non-atomic source claim or redelivery | Use leases/acks and idempotency keys |
| Record disappears after error | Source deleted/acked before processing finished | Reorder ack, use transactions, or add recovery states |
| Shutdown takes a long time | Blocking source or unfinished handlers | Set I/O timeouts, bound draining, and track in-flight work |

Measure poll counts, null-return counts, received message counts, cycle processing durations, errors, and backlogs separately. These metrics distinguish an idle source from a slow source or an adapter failing to send messages.

## 16. Testing MessageSource and polling flows

Test the source separately from the adapter:

- When the source has data, receive() returns a message with the expected payload and headers.
- When the source is empty, receive() returns null.
- When source errors occur, exceptions propagate according to the designed policy.
- When claiming data, two concurrent consumers do not receive duplicates if business requirements disallow it.
- When processing fails, the source has clear redelivery rules or recovery states.

For the flow, test these behaviors:

- The poller triggers the source as configured.
- maxMessagesPerPoll caps message counts as expected.
- The output channel receives messages and downstream is invoked.
- Endpoint start/stop starts and stops the polling schedule.
- Exceptions are handled through error handlers/advice as designed.
- Transaction rollback or commit takes proper effect on the real resource used.

Avoid long Thread.sleep() calls in unit tests. Use fake sources with counters, latches, or suitable test schedulers to verify invocation counts and lifecycle states deterministically.

## 17. Deployment checklist

Before taking a polling source to production, verify:

- Does the source implement MessageSource per contract, returning null when empty and not swallowing exceptions?
- Does receive() have timeouts and bounded execution time?
- Does the trigger fit business latency and source load?
- Is maxMessagesPerPoll appropriately bounded to avoid occupying the scheduler too long in one cycle?
- Does the scheduler have enough threads for shared pollers?
- At what point does the source claim/ack/commit data?
- Can multiple instances pull duplicate data?
- Do transactions wrap the exact operations that must be atomic?
- Are retries bounded and applied only to recoverable errors?
- Does downstream have bounded queues and capacity to handle backlogs?
- Do endpoints have autoStartup and phase aligned with startup/shutdown?
- Does shutdown handle in-flight messages and blocking sources?
- Do metrics distinguish empty polls, source errors, send errors, and slow processing?

When these points are clear, SourcePollingChannelAdapter becomes a predictable intake boundary: which source is queried, when it is queried, how many messages are fetched per cycle, where messages are sent, how errors are handled, and when the adapter stops.

## References

- [Channel Adapters and Inbound Adapters](https://docs.spring.io/spring-integration/reference/channel-adapter.html)
- [Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Annotation Configuration](https://docs.spring.io/spring-integration/reference/configuration/annotations.html)
- [Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)

Note: APIs and defaults may vary by version; cross-check against the dependency versions used by your application.
