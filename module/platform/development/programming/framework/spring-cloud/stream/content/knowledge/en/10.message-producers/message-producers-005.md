# Using @PollableBean for Finite-Stream Suppliers

An event-driven application sometimes needs to read a finite dataset from a database or an external source and emit each element as a message. For example, an order service periodically fetches pending outbox records and publishes them to a destination so other services can process them. In Spring Cloud Stream, you can model this data source with a reactive `Supplier` returning a `Flux<T>`.

The key point is that Spring Cloud Stream normally treats `Supplier<Flux<T>>` as a continuous reactive source: the framework invokes the `Supplier` once to obtain the `Flux` and connects it to the processing pipeline. If the `Flux` actually contains only a finite batch, the `Supplier` needs to be invoked again periodically to fetch the next dataset. The `@PollableBean` annotation marks this exact scenario and enables Spring Cloud Stream to apply polling to a reactive `Supplier`.

This lesson focuses on choosing the right source model, configuring the poller, splitting elements into messages, managing already-emitted data, and testing. Examples use Java, Spring Cloud Stream, and Project Reactor; dependencies, binder configurations, and certain operational details should be verified against your Spring Cloud version.

## Learning Objectives

After this lesson, you will be able to:

- Explain why a regular `Supplier<Flux<T>>` is typically initialized only once.
- Distinguish continuous reactive sources from reactive sources returning finite datasets.
- Use `@PollableBean` to mark a `Supplier<Flux<T>>` that needs periodic re-invocation.
- Understand the `splittable` attribute and its impact on the number of emitted messages.
- Configure the output binding and poller for a finite source.
- Design batch queries, cursors, or outboxes so each poll fetches appropriate data.
- Handle errors, duplicate messages, asynchronous testing, and source observability.

## 1. The Problem: A Reactive Supplier Whose Data Has an End

Spring Cloud Stream supports three primary functional forms:

| Function Form | Input | Output | Typical Trigger |
|---|---|---|---|
| Supplier<T> | None | A value T | Poller invokes periodically |
| Function<T, R> | A message T | A result R | Incoming message triggers |
| Consumer<T> | A message T | None | Incoming message triggers |

A `Supplier` has no input binding to receive trigger events. The framework needs another mechanism to call `get()`. With an imperative `Supplier<T>`, each invocation normally produces one value and the default poller calls it periodically.

`Supplier<Flux<T>>` has different semantics. Its `get()` method returns a `Publisher`—that is, a description of a data stream. In the standard reactive model, the framework calls the `Supplier` once to obtain the `Flux` and then subscribes to consume that stream. This suits a long-lived source such as a `Flux` emitting events continuously.

However, some sources return a finite `Flux`. Examples:

- A JDBC or R2DBC query returning currently available records.
- A single file read returning a list of lines.
- An external API returning one page of results.
- An outbox table holding events waiting to be emitted.
- A periodic job generating a batch of events to send.

Once the `Flux` completes, no more elements are emitted from that invocation. If the `Supplier` was only called once, the next query will not happen automatically. This is where the `Supplier` needs to be marked as pollable.

## 2. What Is @PollableBean?

`@PollableBean` is a marker annotation in Spring Cloud Function, with the fully qualified name:

~~~java
org.springframework.cloud.function.context.PollableBean
~~~

This annotation marks a reactive `Supplier` that produces a finite stream and needs to be re-invoked via the integration framework's polling mechanism. When used with Spring Cloud Stream, the integration layer recognizes this marker and registers the `Supplier` with the poller so each cycle can obtain a new `Flux`.

An important point: Spring Cloud Function only provides the marker semantics of the annotation; Spring Cloud Function itself does not create a scheduler or perform polling. The polling behavior is provided by the integration framework—in this case, Spring Cloud Stream.

Minimal example:

~~~java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

public class GreetingSource {

    @PollableBean
    public Supplier<Flux<String>> greetings() {
        return () -> Flux.just("hello", "see you soon");
    }
}
~~~

Each time the `Supplier` is invoked, it returns a finite `Flux` with two elements. `PollableBean` indicates that this source should be re-invoked instead of treating the first `Flux` as a permanent continuous stream.

Because `@PollableBean` already serves as a bean declaration, the example method uses it directly. There is no need to place `@Bean` on the same method as well. Use the exact package and dependencies provided by your compatible Spring Cloud Function/Spring Cloud Stream version.

## 3. Distinguishing Three Supplier Patterns

### 3.1. Imperative Supplier Producing One Value Each Time

When a `Supplier` returns a single object, each poll produces one message:

~~~java
@Bean
public Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat(Instant.now());
}

record Heartbeat(Instant createdAt) {}
~~~

This is the right choice when each invocation creates only one value. You do not need `@PollableBean` to turn an imperative `Supplier` into a periodic source; the default poller already supports this pattern.

### 3.2. Continuous Reactive Supplier

A `Supplier` returning a long-lived `Flux` is normally invoked once:

~~~java
@Bean
public Supplier<Flux<Heartbeat>> heartbeatStream() {
    return () -> Flux.interval(Duration.ofSeconds(1))
            .map(tick -> new Heartbeat(Instant.now()));
}
~~~

`Flux.interval` emits elements over time and does not complete on its own. This is a continuous reactive source. Do not annotate this source with `@PollableBean`, because calling the `Supplier` repeatedly on a schedule can spawn multiple continuous streams and unintended multiple subscriptions.

### 3.3. Finite Reactive Supplier

A `Supplier` returning a finite `Flux` needs to be called again to read the next dataset:

~~~java
@PollableBean
public Supplier<Flux<Heartbeat>> finiteHeartbeatBatch() {
    return () -> Flux.just(
            new Heartbeat(Instant.now()),
            new Heartbeat(Instant.now()));
}
~~~

This is the exact use case for `@PollableBean`. Each poll creates a finite `Flux`, the elements are consumed, the `Flux` completes, and the next cycle can call the `Supplier` to fetch new data.

| Criterion | Supplier<T> | Continuous Supplier<Flux<T>> | Finite Supplier<Flux<T>> |
|---|---|---|---|
| Return value | A single value | A long-lived Publisher | A Publisher that terminates |
| Typical behavior | Poll value by value | Subscribe once | Poll to fetch multiple batches |
| Annotation | @Bean | @Bean | @PollableBean |
| Example | Heartbeat per call | Flux.interval | Querying a page of data |

Do not choose the annotation merely because the return type contains the word `Flux`. Consider the actual lifecycle of the `Publisher`: does it complete after each batch, or does it keep emitting data over a long period?

## 4. The splittable Attribute

`@PollableBean` has a `splittable` attribute. Its default value is `true`. When `true`, the resulting `Flux` is split into individual elements and each element is emitted as a separate message.

Example:

~~~java
@PollableBean(splittable = true)
public Supplier<Flux<String>> names() {
    return () -> Flux.just("An", "Binh", "Chi");
}
~~~

In a single polling cycle, the `Supplier` produces three elements. With the default splitting mode, the output binding receives three messages:

~~~text
Message 1: An
Message 2: Binh
Message 3: Chi
~~~

This is usually the right option for event streaming: each record is an independent unit of data that can be routed, partitioned, acknowledged, and processed individually.

If you set `splittable = false`, the framework keeps the `Flux` unsplit at this step. That usage only makes sense when downstream processing and the message converter/binder support representing the result in the desired format. Do not assume every broker can serialize a `Flux` object into a batch payload. Verify the actual message format with an integration test.

| Setting | Meaning | Suitable Case |
|---|---|---|
| splittable = true | Split each Flux element into an individual message | Each record is an independent event |
| splittable = false | Do not split the Flux in the splitter step | Downstream intentionally treats the result as a single unit |

Default usage example:

~~~java
@PollableBean
public Supplier<Flux<OrderCreated>> orderEvents() {
    return () -> repository.findPendingEvents();
}
~~~

Explicit example:

~~~java
@PollableBean(splittable = false)
public Supplier<Flux<OrderBatch>> orderBatches() {
    return () -> repository.findPendingBatches();
}
~~~

The second example only makes sense if the actual payload type and application converter support sending the result as a single unit. If the business requirement is to send a JSON array, consider constructing an explicit batch type like `List<OrderCreated>` or `OrderBatch` and testing serialization, rather than assuming a `Flux` automatically becomes a JSON array.

## 5. Building a Batch-Reading Source

A useful finite source must return fresh data on each invocation. The following example models a service reading events from an outbox:

~~~java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
class OrderEventSource {

    private final OrderOutboxRepository repository;

    OrderEventSource(OrderOutboxRepository repository) {
        this.repository = repository;
    }

    @PollableBean(splittable = true)
    Supplier<Flux<OrderCreated>> pendingOrders() {
        return () -> Flux.defer(() ->
                repository.claimNextBatch(100)
                        .map(OutboxRecord::toOrderCreated));
    }
}

interface OrderOutboxRepository {
    Flux<OutboxRecord> claimNextBatch(int limit);
}

record OutboxRecord(String eventId, String orderId, String customerId) {
    OrderCreated toOrderCreated() {
        return new OrderCreated(eventId, orderId, customerId);
    }
}

record OrderCreated(String eventId, String orderId, String customerId) {}
~~~

This example illustrates the repository boundary; `claimNextBatch` must be implemented using queries and status-update mechanisms suited to the database. A method name alone does not guarantee records are locked or marked. The implementation must ensure two instances do not unintentionally claim the same batch.

`Flux.defer` delays creating the source publisher until subscription time. This is helpful when each subscription needs to execute a fresh query. Also understand how your repository is implemented: some APIs return a cold `Flux` that executes only upon subscribe, while others may start the operation immediately when the method is called.

### 5.1. Never Re-Read the Same Records Indefinitely

Suppose every poll executes:

~~~sql
SELECT *
FROM order_outbox
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 100;
~~~

If record status does not change after sending, the next poll will read the exact same 100 records again. As a result, the producer emits duplicate messages endlessly.

The source needs an explicit progress strategy:

- Claim records in a transaction and transition their status to `PROCESSING`.
- Assign a lease or expiration timestamp so records can be reclaimed if a worker fails.
- Mark `SENT` only after confirming send results per the delivery guarantee required by the application.
- Store a stable event ID so consumers can recognize duplicate messages.
- Bound the number of records in a batch to control memory and processing time.

With multiple producer instances, claiming must be atomic. You can use row locks, conditional update statements, `SKIP LOCKED` if supported by the database engine, or an equivalent lease mechanism. SQL syntax and transaction isolation levels depend on the database engine in use.

### 5.2. Pagination and Cursors

If data can grow rapidly, avoid loading the entire dataset into memory. Choose a batching strategy:

| Strategy | How It Works | Notes |
|---|---|---|
| Limit/offset | Read a slice by position | Large offsets can be slow; mutating data can shift pages |
| Key-based cursor | Read records with keys greater than the last processed key | Requires a stable sort key and handling of late-arriving records |
| Status-based claim | Transition records to an in-progress state while fetching | Must include leases and reclamation when a worker dies |
| Outbox relay | Read unpublished outbox records and forward them | Requires careful transaction, retry, and idempotency design |

For business event sources, an outbox relay is usually easier to control than an arbitrary query over business tables because the outbox explicitly stores event ID, payload, event type, and publish state.

### 5.3. Keep Batches Finite and Bounded

A poll cycle should have a finite completion time and predictable data volume. Set record count limits, query timeouts, processing time bounds, and a policy for when the data source is unresponsive.

Do not return `Flux.interval`, `Flux.never`, or a publisher that never completes from a `Supplier` annotated with `@PollableBean`. A poll cycle needs an ending so the next cycle can operate as intended.

## 6. Configuring the Output Binding and Poller

Suppose a bean is named `pendingOrders` with type `Supplier<Flux<OrderCreated>>`. By functional binding convention, the output binding is `pendingOrders-out-0`.

~~~yaml
spring:
  cloud:
    function:
      definition: pendingOrders
    stream:
      bindings:
        pendingOrders-out-0:
          destination: orders.created
          content-type: application/json
  integration:
    poller:
      fixed-delay: 5000
      initial-delay: 1000
~~~

Meaning:

- `spring.cloud.function.definition` selects the function bean to bind.
- `pendingOrders-out-0` is the `Supplier`'s output binding.
- `destination` specifies the topic, queue, or corresponding resource mapped by the binder.
- `content-type` declares the payload format so message conversion occurs consistently.
- `fixed-delay` sets the interval between default poller triggers in milliseconds.
- `initial-delay` delays the first trigger.

Under this configuration, the poller starts after one second and then triggers with a five-second delay. Each `Supplier` invocation must produce a fresh finite `Flux`. With default `splittable`, each element of the `Flux` is emitted as a separate message.

If the application has multiple output bindings needing different polling cadences, you can configure per-binding pollers instead of relying on a single global configuration. Verify exact syntax and properties against the documentation for your Spring Cloud Stream version.

### 6.1. Default Poller and Message Limits

Spring Cloud Stream uses the default poller mechanism for `Supplier`. Current documentation describes properties such as `fixedDelay`, `maxMessagesPerPoll`, `cron`, `initialDelay`, and `timeUnit` under the `spring.integration.poller` prefix.

`maxMessagesPerPoll` limits the number of messages per polling event of the default poller. When a reactive source is split into multiple messages, test the actual behavior of your framework version and binder; do not confuse the poller limit with the batch size returned by your database query. Source-layer batch limits should be designed separately in the repository.

Do not lower `fixed-delay` excessively to compensate for a slow query. Measure cycle duration, throughput, and source latency before choosing a polling schedule.

## 7. Data Path from Source to Broker

~~~mermaid
flowchart TD
    A[Default poller reaches schedule] --> B[Calls Supplier.get]
    B --> C[Creates new finite Flux]
    C --> D[Reads or claims a batch of data]
    D --> E{Flux has elements?}
    E -->|Yes| F{splittable?}
    F -->|true| G[Split each element into a message]
    F -->|false| H[Keep Flux result unsplit]
    G --> I[Output binding]
    H --> I
    I --> J[Binder]
    J --> K[(Kafka / RabbitMQ / Pulsar)]
    E -->|No| L[Emit no messages this cycle]
    K --> M[Consumer receives and processes]
~~~

Components have distinct responsibilities:

1. The poller decides when to invoke the `Supplier`.
2. The `Supplier` constructs the `Publisher` for the current read.
3. The repository or adapter reads data from the source.
4. `PollableBean` signals that this reactive `Supplier` needs to be re-invoked via polling.
5. The splitter handles the `splittable` attribute.
6. The output binding and binder deliver messages to the destination.
7. Downstream consumers handle event processing and deduplication when required.

If the `Flux` is empty, that cycle produces no messages. This can be a normal state when no records are waiting to be processed.

## 8. Error Handling Within a Poll Cycle

A finite source can fail when querying a database, calling an API, reading a file, or converting payloads. Classify errors to choose the appropriate behavior:

- Transient errors such as timeouts or dropped connections can be retried with backoff.
- Data errors such as invalid records must be logged, quarantined, or routed to an error-handling workflow.
- Configuration errors such as bad credentials or missing destinations require alerting and configuration fixes.
- Programming errors must be logged with sufficient context and not retried blindly forever.

With a reactive source, error handling can be placed inside the pipeline:

~~~java
@PollableBean
Supplier<Flux<OrderCreated>> pendingOrders() {
    return () -> Flux.defer(() -> repository.claimNextBatch(100))
            .map(OutboxRecord::toOrderCreated)
            .doOnError(error ->
                    log.error("Cannot read pending order events", error));
}
~~~

This snippet illustrates logging the error; it does not establish a complete retry policy on its own. If using `retryWhen`, cap the retry attempts, use bounded backoff, and define how leases are released for records that were claimed but not successfully emitted.

Do not assume consumer-binding retries will automatically resolve errors originating inside a reactive `Supplier`. A reactive pipeline has its own lifecycle and error semantics; test errors occurring before any element, errors mid-stream, and errors when the binder sends messages.

### 8.1. Do Not Mark as Sent Before Obtaining a Result

Suppose the producer updates a record to `SENT` immediately after querying, before the binder sends the message. If the broker loses connectivity at that moment, the record is already marked complete while the message never arrived. That is an event-loss risk.

Conversely, if the broker already received the message but the producer missed the acknowledgment due to a timeout and resends, the message can be duplicated. This is a common scenario in distributed systems.

An outbox relay workflow typically requires:

1. Claiming a batch of records with a time-limited lease.
2. Emitting messages with a stable event ID.
3. Recording send outcomes according to the binder/broker confirmation mechanism.
4. Marking completion only after receiving an appropriate outcome.
5. Reclaiming or allowing re-claiming of expired leases.
6. Using idempotency in consumers to safely handle re-emissions.

Sending a message and updating database state usually do not occur inside a single atomic transaction. Therefore, the design should accept at-least-once delivery and guard against duplicate effects on the receiving side, unless the system uses a specific transactional mechanism proving a different guarantee.

## 9. Delivery Guarantees and Idempotency

`@PollableBean` governs how a reactive `Supplier` is polled; it does not by itself guarantee exactly-once message delivery. The final guarantee also depends on the binder, broker, acknowledgments, producer confirms, transactions, and application state-update logic.

For safe processing:

- Assign a unique, immutable event ID to each event.
- Have consumers record processed event IDs or enforce a unique constraint.
- Make state-update operations idempotent.
- Use an outbox to decouple persisting business events from sending them through the broker.
- Provide leases or recovery mechanisms for records claimed by a crashed worker.
- Track counts of pending, processing, sent, and overdue records.

For example, a consumer can record the event ID before applying business changes within the same database transaction. If the event ID already exists, the consumer skips the duplicate side effect and returns an appropriate processing status.

Do not use polling timestamps or attempt numbers as event IDs. Those values change across runs and do not stably identify a business event.

## 10. Testing Finite Suppliers

Test across multiple layers because unit tests for `Flux` do not verify poller schedules, bindings, or broker semantics.

### 10.1. Unit Testing with StepVerifier

For reactive sources, `StepVerifier` helps assert elements and completion signals:

~~~java
class PendingOrderSourceTest {

    @Test
    void returnsFiniteBatch() {
        OrderOutboxRepository repository = limit ->
                Flux.just(
                        new OutboxRecord("e-1", "o-1", "c-1"),
                        new OutboxRecord("e-2", "o-2", "c-2"));

        OrderEventSource source = new OrderEventSource(repository);
        Flux<OrderCreated> events = source.pendingOrders().get();

        StepVerifier.create(events)
                .expectNextMatches(event -> event.eventId().equals("e-1"))
                .expectNextMatches(event -> event.eventId().equals("e-2"))
                .verifyComplete();
    }
}
~~~

This tests the data and completion signal conceptually. In real code, the `Supplier` method may be exposed as a bean factory method, and tests should retrieve the bean from the Spring context when verifying wiring or proxies.

### 10.2. Verifying Fresh Data on Each Invocation

An important test is verifying that the `Supplier` can be called multiple times and receives fresh results each time:

~~~java
AtomicInteger pollCount = new AtomicInteger();

@PollableBean
Supplier<Flux<Integer>> counterBatch() {
    return () -> Flux.just(pollCount.incrementAndGet());
}
~~~

When `get()` is called twice, the source returns two distinct batches. You can use a counter or fake repository to verify the number of queries. This test catches accidentally creating a single `Flux` outside the lambda and reusing the same result on every cycle.

### 10.3. Testing Bindings with the Test Binder

The Spring Cloud Stream Test Binder allows sending and receiving messages in memory. For a polled `Supplier`, tests should wait asynchronously for messages with a bounded timeout:

~~~java
@SpringBootTest(properties = {
        "spring.cloud.function.definition=pendingOrders",
        "spring.integration.poller.fixed-delay=100"
})
class PendingOrderBindingTest {

    @Autowired
    OutputDestination output;

    @Test
    void publishesEachElementAsMessage() {
        Message<byte[]> first =
                output.receive(3000, "pendingOrders-out-0");

        assertNotNull(first);
    }
}
~~~

This example only sketches waiting for a message; real tests must configure the test binder, repository test double, and destination according to your dependency version. If `splittable` is `true`, receive all expected messages and verify each payload rather than checking only the first message.

### 10.4. Integration Testing with a Real Broker

The Test Binder does not fully simulate broker persistence, send acknowledgments, partition distribution, connection recovery, or redelivery. For critical flows, add integration tests with the actual broker:

- Kafka: verify topic, partition, key, producer acknowledgment, and consumer group.
- RabbitMQ: verify exchange, queue, routing, publisher confirms, and dead-lettering.
- Pulsar: verify topic, subscription, acknowledgments, and redelivery.
- Outbox: verify concurrent claiming, lease expiration, broker disconnects, and resending.

Also test empty `Flux`, full batches, batches larger than expected limits, repository timeouts, mid-emission failures, and abrupt application shutdowns.

## 11. Operating and Observing a Polled Source

A polled source may work in development yet cause high load or duplicate emissions when deployed across multiple instances. Monitor the following metrics:

| Metric | Meaning |
|---|---|
| Poll count | Confirms the poller remains active on schedule |
| Poll duration | Detects slow queries or prolonged processing |
| Elements per Flux | Tracks batch sizes |
| Successful/failed published messages | Measures publishing outcomes |
| Pending/processing/sent record counts | Tracks outbox progress |
| Age of oldest pending record | Detects stalled backlogs |
| Expired lease count | Detects crashed workers or overly slow processing |
| Duplicate event ID count at consumer | Detects redeliveries or duplicate producer emissions |

Set batch and query-time limits so a single cycle does not consume excessive resources. If multiple instances run the `Supplier`, clarify whether each instance reads the same dataset or partitions the work. For a shared outbox source, atomic claiming is mandatory to prevent all instances from emitting the same batch.

The poller may run on framework-managed threads. Do not rely on a specific thread or `ThreadLocal` to hold business state. If you need thread control when emitting messages from an external event-driven source, consider `StreamBridge` or an appropriate adapter instead of forcing a continuous source into a polling model.

During shutdown, allow in-flight tasks to finish within a bounded timeout or let leases expire so another instance can reclaim them. Do not mark records complete merely because the application is shutting down.

## 12. When to Use @PollableBean vs. Alternatives?

| Scenario | Suitable Choice |
|---|---|
| Each invocation produces a single value | Supplier<T> |
| Long-lived continuous reactive source | Standard Supplier<Flux<T>> |
| Reactive source querying a finite set and completing | @PollableBean Supplier<Flux<T>> |
| Data comes from HTTP, callbacks, or another event-driven system | StreamBridge or integration adapter |
| Application needs to decide when to read each incoming message | PollableMessageSource |
| Need stateful processing by key, window, or aggregate on Kafka | Kafka Streams |

Do not confuse `@PollableBean` with `PollableMessageSource`. `@PollableBean` marks a reactive `Supplier` producer so the framework re-invokes it periodically. `PollableMessageSource` is a consumer model allowing the application to explicitly call `poll()` to fetch incoming messages. The two mechanisms have opposite data directions and control flows.

## 13. Common Mistakes

1. **Using a plain `Supplier<Flux<T>>` for a finite dataset**: the `Supplier` may be invoked only once, preventing subsequent reads. Annotate finite sources with `@PollableBean`.
2. **Annotating an infinite source with `@PollableBean`**: each poll cycle can spawn another continuous stream. Use a plain reactive `Supplier` for long-lived sources.
3. **Creating the `Flux` once outside the lambda**: cycles may reuse the same `Publisher` or stale data. Create a new query/publisher inside each `Supplier` invocation.
4. **Not updating emitted record state**: the poller re-reads the same records on the next cycle. Use claims, cursors, or outbox state.
5. **Using `splittable = false` without testing the converter**: the `Flux` may not serialize into the message format the binder expects. Test actual payloads or use an explicit batch type.
6. **Confusing `fixed-delay` with batch size**: the polling interval does not limit how many records a repository returns. Set batch limits separately.
7. **Not controlling multiple instances**: instances may fetch the same set of records concurrently. Use atomic claiming or work partitioning.
8. **Marking `SENT` before sending**: broker errors can lose events. Update status based on send results and include lease reclamation.
9. **Assuming retries prevent message loss or duplicates**: retries can introduce duplicates when send outcomes are indeterminate. Design event IDs and idempotency.
10. **Not testing the completion signal**: a source intended to be finite that never completes can stall polling cycles. Use `StepVerifier` to assert `verifyComplete`.
11. **Not monitoring backlog**: the source may keep polling while falling behind incoming data volume. Measure pending record age, processing duration, and emitted message counts.

## 14. Workflow for Implementing a Finite Source

When building a new source, follow this sequence:

1. Identify the data source and the criteria qualifying a record for emission.
2. Choose an imperative or reactive `Supplier` based on item count per invocation.
3. If using `Supplier<Flux<T>>`, determine whether the `Publisher` is finite or continuous.
4. Annotate finite sources with `@PollableBean`.
5. Choose `splittable` to decide between emitting each element or keeping the result as one unit.
6. Set batch limits, cursors, or claiming mechanisms per cycle.
7. Configure function definition, output binding, destination, and poller.
8. Design event IDs, outbox states, leases, retries, and idempotency.
9. Write unit tests for data and completion, Test Binder tests for the output binding, and integration tests for the broker.
10. Monitor polling duration, batch size, backlog, and publish errors in production.

## Conclusion

`@PollableBean` solves a specific case in the functional model: a reactive `Supplier` returning a finite stream that needs to be invoked periodically to fetch new batches of data. This annotation signals intent to the integration framework; Spring Cloud Stream provides the poller mechanism that performs re-invocation. The default `splittable` attribute splits each element into a separate message.

For reliable operation, each invocation must create a fresh finite `Flux`, data must be bounded, and read progress must be managed explicitly. With outbox or database sources, combine claim/lease mechanics, event IDs, and idempotency to handle redeliveries safely. Polling only determines when data is read; it does not by itself guarantee exactly-once delivery.

## References

- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
