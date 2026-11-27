# Supplier<Flux<T>> and Stream Subscription Lifecycle

In Spring Cloud Stream, a Supplier is a data emission source. When a Supplier returns a single value, the framework can call its get() method on a polling schedule to fetch each value and send it to the broker. When a Supplier returns Flux<T>, the semantics change: the return value is a reactive data stream that can emit multiple elements over time. The framework needs to know whether it is a continuous stream subscribed to only once or a finite result that needs to be queried periodically.

Understanding the subscription lifecycle properly helps avoid two common mistakes: a finite stream running only once and completing even though polling was intended, or a continuous stream being recreated on every poll tick and causing duplicate emissions. Spring Cloud Stream supports both cases, but the declarations differ.

## 1. How Do Supplier<T> and Supplier<Flux<T>> Differ?

A regular Supplier returns one value per invocation:

~~~java
@Bean
public Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat(Instant.now());
}
~~~

Spring Cloud Stream uses the default poller to invoke this Supplier. Under the default configuration, the poller triggers once per second and fetches one value each time to send through the output binding.

With a reactive Supplier, get() returns a Publisher instead of a single value:

~~~java
@Bean
public Supplier<Flux<Heartbeat>> heartbeatStream() {
    return () -> Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> new Heartbeat(sequence, Instant.now()));
}
~~~

Here, a single call to get() creates a Flux capable of emitting multiple heartbeats. With a standard reactive Supplier, Spring Cloud Stream recognizes this return type and calls get() once to obtain the stream. The framework subscribes to the Publisher and lets elements be emitted over time. It does not invoke get() again every second as it does for Supplier<Heartbeat>.

| Characteristic | Supplier<T> | Regular Supplier<Flux<T>> |
|---|---|---|
| Return value | One object per invocation. | A Publisher capable of emitting multiple objects. |
| Triggering mechanism | Poller invokes get() periodically. | Framework obtains the Publisher once and subscribes to the stream. |
| Example | One heartbeat per poll. | A continuous heartbeat stream emitting every second. |
| When the stream ends | The next poll invokes the Supplier again. | The Publisher completes; the Supplier is not automatically re-invoked just because the Flux completed. |
| Suitable for | Fetching one record or value periodically. | Continuous event sources or long-lived streams. |

Key takeaway: **one Supplier invocation does not mean one message**. With Supplier<Flux<T>>, one invocation can provide a stream emitting zero, one, or many messages.

## 2. How Does Stream Subscription Happen?

For a reactive Supplier bound to a broker, the high-level lifecycle consists of the following steps:

~~~mermaid
flowchart TD
    A[Spring initializes ApplicationContext] --> B[Register Supplier bean]
    B --> C[Select function definition]
    C --> D[Create output binding]
    D --> E[Call Supplier.get once]
    E --> F[Receive Flux Publisher]
    F --> G[Framework subscribes]
    G --> H[Flux emits elements]
    H --> I[Output binding sends messages to broker]
    G --> J[Application or binding stops]
    J --> K[Subscription terminates per endpoint lifecycle]
~~~

Function names still follow Spring Cloud Stream's binding convention. If the bean is named **heartbeatStream**, the default output binding is **heartbeatStream-out-0**.

Configuration example:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeatStream
    stream:
      bindings:
        heartbeatStream-out-0:
          destination: heartbeat-events
          content-type: application/json
~~~

When the application starts, the output binding is connected to the **heartbeat-events** destination. The framework retrieves the Flux from the Supplier and subscribes to the stream so emitted elements are sent through that binding.

There is no need to call subscribe() manually inside the Supplier. Return the Publisher so the framework can manage the binding's subscription. If you call subscribe() inside the Supplier and return another Flux, the self-created stream may have nothing to do with the output binding; errors and subscription cancellation also become difficult to manage alongside the application lifecycle.

## 3. Continuous Streams vs. Finite Streams

A reactive Supplier is commonly used as a continuous source. For example, Flux.interval emits a value periodically and continues until cancelled:

~~~java
@Bean
public Supplier<Flux<Heartbeat>> heartbeatStream() {
    return () -> Flux.interval(Duration.ofSeconds(2))
            .map(sequence -> new Heartbeat(sequence, Instant.now()));
}
~~~

Conversely, Flux.just emits only the declared elements and then completes:

~~~java
@Bean
public Supplier<Flux<String>> startupMessages() {
    return () -> Flux.just("service-started", "service-ready");
}
~~~

With a regular reactive Supplier, the framework invokes get() only once. Therefore, startupMessages emits two elements and completes; it does not automatically re-run every second. If the goal is to periodically query a data source and return a finite batch, use @PollableBean.

### Using @PollableBean for a Finite Flux

@PollableBean (from package **org.springframework.cloud.function.context**) is an annotation marking a reactive Supplier that produces a finite stream needing to be polled. This annotation is a bean declaration; the Spring Cloud Stream integration framework uses that marker to invoke the Supplier on the poller schedule.

Example of a repository returning pending orders:

~~~java
@Configuration
public class PendingOrderSource {

    @PollableBean(splittable = true)
    public Supplier<Flux<OrderEvent>> pendingOrders(
            OrderRepository repository) {
        return () -> Flux.defer(() ->
                Flux.fromIterable(repository.fetchNextBatch()))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Select this bean as the function and configure the output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: pendingOrders
    stream:
      bindings:
        pendingOrders-out-0:
          destination: pending-order-events
          content-type: application/json
~~~

On each poll, the Supplier returns a finite Flux representing the current batch of orders. Flux.defer defers calling fetchNextBatch() until the Publisher is subscribed to, so each poll can retrieve a fresh batch. subscribeOn(Schedulers.boundedElastic()) is appropriate when the repository query is blocking; if the repository is already reactive, switching to this scheduler is unnecessary.

Default poller configuration:

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 5000
      max-messages-per-poll: 1
~~~

The example above sets the default delay between polls to 5 seconds. The max-messages-per-poll property limits the number of messages emitted per poll event under the poller mechanism. If you only want to change the polling schedule for a specific output binding, use per-binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        pendingOrders-out-0:
          producer:
            poller:
              fixed-delay: 5000
              max-messages-per-poll: 1
~~~

Poller properties control how often the Supplier is invoked. They do not control the emission rate of individual elements inside a continuous Flux. Two concepts must be kept separate:

- **Polling:** when the framework invokes Supplier.get() to obtain a new Publisher.
- **Subscription:** subscribing to the Publisher to receive the elements that the Publisher emits.

### The splittable Attribute

@PollableBean has a splittable attribute, which defaults to true. When enabled, the framework splits the elements of the returned Flux into separate messages sent via the output binding.

~~~java
@PollableBean(splittable = true)
public Supplier<Flux<OrderEvent>> pendingOrders(
        OrderRepository repository) {
    return () -> Flux.fromIterable(repository.fetchNextBatch());
}
~~~

If splittable = false is set, the framework does not split elements into individual messages via this mechanism; the Flux result is kept as a single poll result. Choose that option only when the payload type and sender/receiver converters or binders are designed to handle that representation. For typical event streams, splittable = true is usually more suitable because each element becomes an independent message.

## 4. Choosing the Right Flux Source

A Flux can be a cold publisher or a hot publisher. This distinction affects when data is produced and whether events can be missed before the framework subscribes.

| Publisher Type | Behavior | Example |
|---|---|---|
| Cold | Work begins upon subscription; each subscription typically creates an independent execution. | Flux.just, Flux.fromIterable, Flux.defer, Flux.interval. |
| Hot | The source can emit independently of subscribers; late subscribers may miss already-emitted elements. | Some event sources using Sinks.Many or an event bus. |

With a cold publisher, the framework subscribes once and the source begins emitting when subscribed. Example:

~~~java
Supplier<Flux<String>> source = () ->
        Flux.defer(() -> {
            log.info("Starting stream creation");
            return Flux.just("A", "B", "C");
        });
~~~

Flux.defer is useful when you need to create the source at subscription time rather than at bean initialization time. However, for a continuous reactive Supplier that the framework subscribes to once, defer does not turn the stream into a periodic polling mechanism.

With a hot publisher, make sure the source does not emit critical data before the subscription is established, or pick an appropriate buffering/replay mechanism. A multicast Sinks.Many does not replay previously emitted elements to late subscribers unless you use a sink flavor with a corresponding retention/replay policy.

Do not use an in-memory hot source as durable storage. When the process stops, data and state in an in-memory sink can be lost.

## 5. Do Not Block the Reactive Processing Thread

Reactor enables expressing asynchronous operations as chains of operators. For a continuous Supplier, avoid calling blocking APIs directly on schedulers dedicated to timer signals or event loops.

Example of a lightweight event emission source:

~~~java
@Bean
public Supplier<Flux<SystemMetric>> metricsStream() {
    return () -> Flux.interval(Duration.ofSeconds(5))
            .map(tick -> new SystemMetric(
                    tick,
                    Instant.now(),
                    Runtime.getRuntime().freeMemory()
            ));
}
~~~

If the data source is a blocking API or JDBC, defer the call and offload the blocking part to boundedElastic:

~~~java
Supplier<Flux<CustomerEvent>> customerEvents(
        LegacyCustomerClient client) {
    return () -> Flux.defer(() ->
            Flux.fromIterable(client.fetchEvents()))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Do not put Thread.sleep() inside map of a reactive stream. If you need a periodic tick, use Flux.interval. If you need to periodically query a blocking source, use @PollableBean with a poller and execute the query on an appropriate scheduler.

## 6. Backpressure and Binder Limitations

Reactor supports backpressure via the Reactive Streams protocol: a subscriber can signal its demand for data and the publisher can throttle emission according to that demand. However, using Flux in the function signature does not automatically make the entire path from source to broker end-to-end reactive.

With standard message-channel binders, such as the standard Kafka binder or Rabbit binder, the source and destination are not necessarily Reactive Streams Publishers/Subscribers. The application can use Reactor operators to transform data, but you should not assume the broker will propagate demand backward to the Supplier.

Current documentation notes that the reactive Kafka binder has been deprecated since Spring Cloud Stream 4.3.0 and is planned for removal in a future release. For new projects, do not default to choosing that binder solely to get backpressure. Use the binder supported for your project version and explicitly design rate limits, buffering, concurrency, retries, and resilience according to the binder's actual mechanics.

If the source emits faster than the broker can send, you need a clear strategy:

- Limit the rate or number of elements generated.
- Use a bounded-capacity buffer and define behavior when the buffer is full.
- Drop data only when the business logic allows it, such as non-critical metrics.
- For business events, persist the source in a durable system and replay when needed.
- Monitor queue depth, producer errors, send latency, and dropped element counts.

Do not use an unbounded buffer to mask a slow downstream. An unboundedly growing buffer can exhaust the heap and crash the process.

## 7. Errors, Retries, and Publisher Completion

A reactive Supplier is invoked by the framework to obtain a Publisher. Once the stream is connected, per-element error handling resides within the Reactor operators built by the application. Retry mechanisms designed for imperative functions do not automatically wrap every signal of a reactive stream.

Example of error handling with retry:

~~~java
@Bean
public Supplier<Flux<PriceTick>> priceTicks(PriceClient client) {
    return () -> Flux.defer(client::streamTicks)
            .retryWhen(Retry.backoff(
                    Long.MAX_VALUE,
                    Duration.ofSeconds(1))
                    .maxBackoff(Duration.ofSeconds(30)))
            .doOnError(error ->
                    log.error("Unrecoverable price stream error", error));
}
~~~

retryWhen resubscribes to the source upon errors according to the declared policy. Without retry or recovery via onErrorResume, an unhandled error terminates the Publisher. With a regular reactive Supplier, the framework does not automatically call get() again just because the Publisher emitted an error signal.

You can use onErrorResume when the application has an alternative source:

~~~java
return () -> primarySource()
        .onErrorResume(error -> {
            log.warn("Switching to fallback source", error);
            return fallbackSource();
        });
~~~

Choose bounded retries or appropriate backoff. Infinite retries can keep a subscription alive, but can also mask configuration errors or permanent failures. Classify recoverable vs. non-recoverable errors, record metrics for retry counts, and emit alerts when the stream repeatedly falls back.

### When the Flux Completes

A finite Flux emits all elements and then sends an onComplete signal. With a regular reactive Supplier, the Supplier is not automatically called again after completion. If you need to emit a new batch periodically, use @PollableBean.

A continuous Flux such as Flux.interval typically does not complete on its own. It keeps emitting until cancelled or an error occurs. When the application shuts down, the binding/endpoint is stopped along with the application lifecycle; do not treat the internal state of a Publisher as durable state that is automatically restored.

You can use doFinally to observe completion, error, or subscription cancellation:

~~~java
return () -> Flux.interval(Duration.ofSeconds(1))
        .map(this::toHeartbeat)
        .doFinally(signal ->
                log.info("Heartbeat subscription ended: {}", signal));
~~~

doFinally is for observation and resource cleanup. Do not put long-running blocking work in this callback.

## 8. Lifecycle Across Restarts and Multiple Instances

A regular Supplier<Flux<T>> is initialized according to the application lifecycle. When the process starts, the framework creates the binding and subscribes to the Publisher. When the process stops, the corresponding endpoint and subscription are stopped. Upon restart, the application creates a new Supplier/Publisher and subscription.

That means:

- Counters in Flux.interval typically restart from zero in a new process.
- In-memory buffers, counters, and transient Flux state are not automatically recovered.
- An in-memory hot source can lose data when the process stops.
- If resuming from a data position is required, the application must persist checkpoints or use a data source with a durable cursor.

### Running Multiple Replicas

Each application replica typically has its own ApplicationContext and its own subscription to the Supplier. If the Supplier emits heartbeats or generates business events, increasing replicas can proportionally increase emission streams.

For instance, running three replicas with Flux.interval can produce three heartbeat sequences. This is desirable if you want each instance to emit its own liveness status; it is inappropriate if you only want a single business event cluster-wide.

If only one instance is allowed to emit, you need a cluster-level coordination mechanism, such as leader election, distributed locks, or work partitioning. Do not use a static variable or JVM singleton to assume uniqueness across replicas.

## 9. Data Guarantees When Emitting from a Reactive Source

Flux describes how data is emitted within the process. It does not by itself guarantee that data was durably persisted before the binder successfully sends it.

Suppose a Supplier reads records from a database:

1. The Supplier fetches a batch of records.
2. Flux emits the records.
3. The output binding sends each message to the broker.
4. The process stops before updating the checkpoint.

Upon restart, the application may re-read the old batch. This is why consumers should be idempotent and the source needs an explicit cursor/checkpoint. Conversely, if the checkpoint is updated before the message is acknowledged by the broker, a process crash between the two operations can lose data.

For critical business data, consider:

- Transactional outbox to write events in the same business transaction and publish from the outbox.
- CDC or a durable change log if the data source supports it.
- A cursor by unique key or timestamp, updated after ensuring publication under the appropriate workflow.
- Consumer idempotency to tolerate redelivery.
- Dead-lettering and replay procedures for unprocessable messages.

Do not treat Flux.interval, Sinks.Many, or an in-memory collection as a durable queue. Durability after sending also depends on producer configuration, the broker, acknowledgements, and how the application manages source progress.

## 10. Testing Supplier<Flux<T>>

Testing should be separated into three layers:

1. Test the Publisher independently with Reactor StepVerifier.
2. Test the Supplier bean and the number of get() invocations.
3. Spring Cloud Stream integration tests to confirm the binding receives elements and sends them to the right destination.

### Testing a Finite Flux

~~~java
Supplier<Flux<Integer>> source = () -> Flux.range(1, 3);

StepVerifier.create(source.get())
        .expectNext(1, 2, 3)
        .verifyComplete();
~~~

### Testing Time with Virtual Time

For Flux.interval, use virtual time to test without waiting in real time:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3))
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
~~~

### Verifying the Supplier Retrieves the Publisher Only Once

~~~java
AtomicInteger supplierCalls = new AtomicInteger();

Supplier<Flux<String>> source = () -> {
    supplierCalls.incrementAndGet();
    return Flux.just("one", "two");
};

Flux<String> publisher = source.get();

StepVerifier.create(publisher)
        .expectNext("one", "two")
        .verifyComplete();

assertThat(supplierCalls.get()).isEqualTo(1);
~~~

The test above verifies how the Supplier is invoked in a unit test. To verify the framework retrieves the Publisher only once in a real application, start the ApplicationContext with the function definition and test binder, then observe how many times the Supplier is invoked over the binding lifecycle.

### Integration Test Matrix

| Scenario | How to test | Expected outcome |
|---|---|---|
| Continuous reactive Supplier | Start the application and observe the output binding. | Supplier is invoked once; Flux continues emitting multiple messages. |
| Non-pollable finite Flux | Use Flux.just in a regular Supplier. | Elements are emitted once, then the Publisher completes. |
| Finite Flux with PollableBean | Use @PollableBean and a short poller delay in tests. | Supplier is invoked repeatedly on schedule; each run creates a new batch. |
| Splittable true | Return a Flux with three elements. | Three elements are sent as three separate messages. |
| Splittable false | Return a Flux and disable element splitting. | Results are not split into individual messages under this configuration. |
| Mid-stream error | Create a source that errors after several elements. | Retry or fallback executes according to configured Reactor operators. |
| Application shutdown | Close the ApplicationContext while Flux is emitting. | Subscription and endpoint stop along with the application lifecycle. |
| Restart | Restart the context. | New Supplier and subscription are created; source state recovers per application design. |
| Multiple replicas | Run multiple instances with the same configuration. | Number of emission streams and duplicate effects are understood and controlled per cluster requirements. |

When testing with a real broker, verify message counts received, ordering, retries, publish failures, and post-restart behavior. The test binder is useful for in-process binding checks, but it does not replace testing durability, acknowledgements, and load limits on Kafka, RabbitMQ, or Pulsar.

## 11. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Supplier emits only one batch and stops | Finite Flux is used as a continuous reactive Supplier. | Use @PollableBean if periodic polling is needed. |
| Supplier is invoked repeatedly unintentionally | Using @PollableBean for a continuous source or misconfigured poller. | Remove @PollableBean for continuous streams. |
| No output messages | Function not selected, wrong binding name, or Flux emits no elements. | Check definition, output binding, and Publisher. |
| Stream never starts | Supplier returns Publisher but no active binding exists or Publisher depends on another subscription. | Verify binding and let the framework subscribe to the returned Publisher. |
| Data lost before subscriber appears | Using a hot publisher without proper replay/buffer. | Use a cold source, replay, or durable source. |
| Stream dies after one error | onError terminates Publisher and there is no retry/fallback. | Add retryWhen or onErrorResume by error type. |
| Application heap grows | Unbounded buffer or source emits faster than downstream. | Bound buffers, throttle source, and monitor backlog. |
| Duplicate events created when scaling | Each replica runs an independent Supplier. | Use leader election, partitioning, or idempotency. |
| Data re-read after restart | Flux does not store checkpoints and source replays from the beginning. | Manage cursor/checkpoint and make consumers idempotent. |
| Backpressure does not throttle broker | The binder in use does not support end-to-end Reactive Streams. | Check binder capabilities; enforce rate and concurrency limits in the app. |

When investigating, first determine whether the Supplier is continuous or finite. Next, inspect @PollableBean, function definition, output binding, get() call count, subscription timing, and onError, onComplete, or cancel signals. Finally, inspect the binder, broker, and replica count to pinpoint issues at the send boundary.

## 12. Selection Workflow

Before implementing a Supplier<Flux<T>>, answer:

1. Is the data source continuous or does each query return a finite batch?
2. Should the framework retrieve the Publisher once or invoke the Supplier periodically?
3. Is the Publisher cold or hot; can data be missed before subscription?
4. Does the source perform blocking I/O or need a separate scheduler?
5. Can the Flux error or complete; how are retry/fallback defined?
6. Are one or multiple replicas allowed to emit the same event type?
7. Must data and checkpoints survive restarts?
8. Does the binder support end-to-end backpressure or are application-level rate limits needed?

Choose the implementation approach based on the answers:

- **Continuous stream:** use a regular Supplier<Flux<T>>, return a long-lived Publisher, and let the framework subscribe.
- **Finite stream needing periodic execution:** use @PollableBean, configure the poller, and choose splittable based on how elements should be sent.
- **Blocking source:** defer the operation and use an appropriate scheduler, or switch to a genuinely reactive API.
- **Hot source:** manage startup timing, replay/buffering, and behavior when no subscriber is present.
- **Business source requiring durability:** persist a cursor/checkpoint or use outbox/CDC; do not rely on in-memory Flux state.

Supplier<Flux<T>> is how reactive data sources are expressed in Spring Cloud Stream. For continuous streams, the framework retrieves the Publisher and subscribes once; for finite streams needing periodic polling, @PollableBean marks the Supplier for scheduled poller invocations. By clearly separating polling from subscription, handling errors with Reactor, and defining how the data source recovers, the application can emit events more reliably across its deployment lifecycle.

## References

- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
