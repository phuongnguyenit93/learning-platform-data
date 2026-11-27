# Isolating Blocking Operations and Choosing the Right Scheduler

Reactive programming helps process many messages without holding a waiting thread for each I/O operation. However, a Reactor pipeline only delivers its benefits when the operations inside it do not block the thread orchestrating the data stream. Calling synchronous JDBC, a blocking HTTP client, synchronous file reads, or `Thread.sleep()` directly inside an operator can hold the reactive processing thread and slow down many other messages.

Reactor provides `Scheduler` to decide which thread pool a pipeline executes on. For blocking operations, `Schedulers.boundedElastic()` or a dedicated bounded scheduler is typically used. For CPU-bound computations, use `Schedulers.parallel()`. The two operators `subscribeOn` and `publishOn` have different roles: `subscribeOn` affects the subscription process and upstream, whereas `publishOn` shifts execution of subsequent operators onto the chosen scheduler.

## 1. Why Do Blocking Operations Cause Problems in a Reactive Pipeline?

Reactor uses threads to receive signals, orchestrate subscriptions, and execute operators. A few threads may serve multiple message streams or multiple connections concurrently. If an operator invokes a blocking function, the current thread must wait until that function returns.

Unsuitable example:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        LegacyInventoryClient inventoryClient) {

    return events -> events.map(event -> {
        // A synchronous call holds the current thread until it returns.
        Reservation reservation = inventoryClient.reserve(event);
        return OrderResult.from(event, reservation);
    });
}
```

If `reserve()` uses a blocking HTTP client or synchronous JDBC, each invocation holds the thread executing `map()`. When many messages arrive simultaneously, orchestrating threads can become occupied, driving up latency and forcing other streams to wait.

Operations that commonly carry blocking risk:

- Synchronous JDBC/JPA database calls.
- Synchronous HTTP clients such as certain uses of RestTemplate or legacy clients.
- File reads/writes using blocking APIs.
- Calling legacy libraries that use sockets or wait synchronously for responses.
- `Thread.sleep()`, long lock waits, or calling `Future.get()`/`join()` inside the pipeline.

Not every time-consuming operation is blocking. A CPU-bound computation continuously uses CPU without waiting on I/O; it should be scheduled on a thread pool meant for computation, not one intended for blocking I/O.

## 2. Identifying Threads and Execution Models

In a reactive Spring Cloud Stream application, a function can receive and return `Flux` or `Mono`. The binder and framework coordinate subscriptions to connect message streams to the function. Depending on the binder, threads receiving messages, Reactor orchestration threads, and threads executing callbacks can differ.

Do not assume every function runs on a single thread or every binder uses the same thread model. What matters is not holding sensitive event-loop or orchestration threads with blocking operations.

A simple way to observe this is logging thread names inside an operator:

```java
events.doOnNext(event ->
    log.debug("Processing {} on {}",
        event.orderId(),
        Thread.currentThread().getName())
);
```

Thread names aid diagnostics, but should not be treated as a business contract. Threads can change across Reactor versions, binders, and scheduler configurations.

## 3. Common Reactor Schedulers

Reactor provides several common schedulers:

| Scheduler | Characteristics | Suitable workload |
|---|---|---|
| `Schedulers.immediate()` | Executes immediately on the current thread | Cases needing direct execution without thread switching |
| `Schedulers.single()` | A single shared thread | Sequential, lightweight work needing a single execution thread |
| `Schedulers.parallel()` | Thread pool optimized for CPU-bound work | Computations, non-blocking data transformations |
| `Schedulers.boundedElastic()` | Bounded thread pool and queue for blocking work | JDBC, synchronous APIs, file I/O, or legacy libraries |
| `Schedulers.fromExecutorService(...)` | Wraps an application-managed ExecutorService | Need custom executor control or integration with dedicated thread infrastructure |

### boundedElastic for Blocking I/O

`boundedElastic()` is meant for tasks that can wait on I/O. It uses bounded thread resources and a queuing mechanism, avoiding unbounded thread creation when the system has many blocking tasks. This is usually a sensible default for isolating a synchronous call inside a Reactor pipeline.

Even so, bounded elastic does not turn a blocking API into a non-blocking one. A thread is still held while waiting. The scheduler merely isolates that impact from primary orchestration threads and bounds resource usage.

### parallel for CPU-Bound Work

`parallel()` fits CPU-intensive computations that do not wait on I/O, such as scoring, data normalization, or pure-CPU encryption. Do not use `parallel()` for JDBC or blocking HTTP; waiting tasks can occupy all threads reserved for computation.

If there is a heavy computation in the pipeline, you can shift the computation segment to parallel:

```java
Flux<Score> scores = events
    .publishOn(Schedulers.parallel())
    .map(this::calculateScore);
```

Operators after `publishOn` run on that scheduler until another scheduler switch occurs. This example moves the downstream segment to a parallel scheduler worker; it does not automatically turn one computation into multiple parallel computations. To run multiple independent tasks concurrently, explicitly design concurrency, such as using `flatMap` with a concurrency limit.

## 4. Using subscribeOn to Isolate Blocking Calls

For a blocking function that returns a result, a common pattern is wrapping the call with `Mono.fromCallable()` and attaching `subscribeOn(Schedulers.boundedElastic())`:

```java
Mono<Reservation> reservation =
    Mono.fromCallable(() -> inventoryClient.reserve(event))
        .subscribeOn(Schedulers.boundedElastic());
```

`fromCallable()` defers invoking the function until subscription occurs. `subscribeOn()` causes subscription and execution of the upstream source to start on the chosen scheduler. Because the blocking call sits inside the `fromCallable` source, it runs on bounded elastic instead of the thread assembling the pipeline.

In Spring Cloud Stream, you can use this pattern when passing each message through a synchronous service:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        LegacyInventoryClient inventoryClient) {

    return events -> events.flatMap(
        event -> Mono.fromCallable(
                () -> inventoryClient.reserve(event))
            .subscribeOn(Schedulers.boundedElastic())
            .map(reservation ->
                OrderResult.from(event, reservation)),
        8
    );
}
```

The `8` parameter limits how many inner publishers `flatMap` processes concurrently. It helps avoid sending too many simultaneous blocking calls to a service or database. The right value depends on the connection pool, downstream capacity, response times, and application resource limits.

Each blocking call is scheduled on bounded elastic. If a service has a lower concurrency limit, set the `flatMap` limit accordingly instead of raising concurrency arbitrarily. Do not rely on the scheduler as the sole load-throttling mechanism.

## 5. Using publishOn to Shift a Downstream Segment

`publishOn(scheduler)` shifts execution of subsequent operators onto the specified scheduler. It does not change how the upstream source is subscribed to.

Example:

```java
Flux<OrderResult> results = events
    .publishOn(Schedulers.boundedElastic())
    .map(event -> {
        Reservation reservation = inventoryClient.reserve(event);
        return OrderResult.from(event, reservation);
    });
```

After `publishOn`, `map` and subsequent downstream operators run on a bounded elastic worker. This is useful when a contiguous synchronous processing segment needs to run on a separate scheduler.

However, keep in mind:

- Placing `publishOn` before `map` switches the entire downstream segment, not just a single blocking call line.
- If multiple downstream steps are non-blocking, they may also run on bounded elastic until another scheduler switch occurs.
- `publishOn` does not create per-element concurrency by itself; it changes the execution thread.
- If you need to isolate individual blocking calls and limit concurrent calls, the `flatMap + fromCallable + subscribeOn` pattern usually expresses intent more clearly.

Do not place `publishOn` after a blocking operation has already run to try to "fix" it. The scheduler must be applied before the blocking point.

## 6. Distinguishing subscribeOn and publishOn

Both operators accept a `Scheduler`, but their scope of effect differs:

| Criterion | `subscribeOn` | `publishOn` |
|---|---|---|
| Primary effect | Subscription process and upstream source | Downstream operators from its placement onward |
| Typical placement | Near a blocking source, often after `fromCallable` | Before a downstream segment needing a thread switch |
| Used for | Moving source creation/reading onto an appropriate scheduler | Shifting subsequent signal processing to another scheduler |
| Example | `Mono.fromCallable(this::blockingCall).subscribeOn(boundedElastic)` | `flux.publishOn(parallel).map(this::cpuWork)` |

Illustrative example:

```java
Mono<Result> result = Mono.fromCallable(this::blockingRead)
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::transform);
```

The blocking source and upstream are subscribed on bounded elastic. The `map` operator also receives signals from the source executed on that scheduler unless another switch occurs.

Example with `publishOn`:

```java
Flux<Result> result = source
    .map(this::lightweightValidation)
    .publishOn(Schedulers.parallel())
    .map(this::cpuIntensiveTransform)
    .publishOn(Schedulers.boundedElastic())
    .map(this::blockingWrite);
```

Initial validation runs on whatever thread emits signals from source. CPU work is shifted to parallel. The blocking write call is shifted to bounded elastic. In practice, if `blockingWrite` returns a synchronous result and concurrency needs to be managed, `flatMap` with `Mono.fromCallable` can be used instead of a sequential `map` segment.

Do not place multiple `subscribeOn` calls arbitrarily. Typically, one `subscribeOn` near the source establishes where subscription/upstream starts; multiple scheduler switches should be placed deliberately using `publishOn` or inner publishers.

## 7. Integrating Reactive Clients and Blocking Clients

Not every I/O call needs bounded elastic.

### Reactive Client

If a service uses WebClient or R2DBC and the APIs are invoked reactively, chain the publisher directly into the pipeline:

```java
@Bean
Function<Flux<OrderEvent>, Flux<CustomerProfile>> enrichOrders(
        CustomerClient customerClient) {

    return events -> events.flatMap(
        event -> customerClient.findById(event.customerId())
            .map(profile -> profile),
        16
    );
}
```

Suppose `findById()` returns `Mono<CustomerProfile>` and performs non-blocking I/O. There is no need to wrap it in `fromCallable` or switch to bounded elastic. You can bound `flatMap` concurrency to control in-flight requests.

### Blocking Client

If an existing library provides only synchronous methods, isolate the call:

```java
Mono<CustomerProfile> profile =
    Mono.fromCallable(() ->
            legacyCustomerClient.findById(customerId))
        .subscribeOn(Schedulers.boundedElastic());
```

Whenever possible, prefer replacing blocking clients with reactive clients or appropriate non-blocking APIs. Offloading to a scheduler is an integration workaround for synchronous libraries, not a reason to turn the entire application blocking.

## 8. Creating Dedicated Schedulers and Managing Lifecycle

The shared `Schedulers.boundedElastic()` scheduler is usually sufficient for typical blocking calls. If a group of legacy integrations has distinct load characteristics or limits, you can create a dedicated scheduler to isolate resources.

```java
@Configuration
public class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        return Schedulers.newBoundedElastic(
            16,
            1000,
            "legacy-io"
        );
    }
}
```

The illustrative parameters bound the thread count and queue capacity for this scheduler. Choose limits based on downstream capacity, connection counts, timeouts, and expected load. An overly large queue can raise latency and hold excessive pending work in memory; overly low limits can cause rejections or bottlenecks under load spikes.

Inject the scheduler into the function:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        LegacyInventoryClient client,
        Scheduler legacyIoScheduler) {

    return events -> events.flatMap(
        event -> Mono.fromCallable(() -> client.reserve(event))
            .subscribeOn(legacyIoScheduler)
            .map(reservation -> OrderResult.from(event, reservation)),
        8
    );
}
```

A dedicated scheduler must be disposed when the application stops. A bean with `destroyMethod = "dispose"` lets Spring invoke `dispose` during context shutdown. Never create a new scheduler per message; doing so spawns extra thread pools, leaks resources, and makes load hard to control.

## 9. Concurrency Limits, Timeouts, and Backpressure

Moving blocking calls to bounded elastic prevents blocking the event loop, but it does not remove limits of dependent systems. If the application receives messages faster than the database or HTTP service can process them, queues can grow and latency continues to climb.

Coordinate these limits:

- **Concurrency**: limit active inner publishers, such as the concurrency parameter of `flatMap`.
- **Connection pool**: do not send more concurrent calls than available connections or downstream capacity allows.
- **Timeout**: bound client wait times so tasks do not occupy threads for too long.
- **Backpressure**: let subscribers regulate element request rates when sources support backpressure.
- **Queue capacity**: bound scheduler queues and internal buffers.
- **Retry**: avoid retry storms when downstream is overloaded; use backoff and bounded retry counts.

Example limiting concurrency:

```java
Flux<OrderResult> results = events.flatMap(
    event -> Mono.fromCallable(() -> legacyClient.process(event))
        .subscribeOn(Schedulers.boundedElastic()),
    10
);
```

At most 10 inner publishers are subscribed concurrently by this operator. It does not guarantee only 10 threads across the entire application if other pipelines or schedulers share the same pool.

Do not use `parallel()` or add more threads to mask a slow downstream. Measure latency, pending task counts, timeouts, connection pool saturation, and error rates.

## 10. Anti-Patterns to Avoid

### Calling block() Inside the Pipeline

```java
events.map(event ->
    inventoryClient.reserveReactive(event).block()
);
```

Calling `block()` turns a reactive publisher into a synchronous call. Inside a reactive pipeline, this can block signal-emitting threads and forfeit non-blocking benefits. Compose publishers using `flatMap`:

```java
events.flatMap(inventoryClient::reserveReactive);
```

### Manually Calling subscribe() Inside the Function

```java
@Bean
Consumer<Flux<OrderEvent>> process() {
    return events -> events.subscribe(this::handle);
}
```

Do not call `subscribe()` manually to create a detached processing flow inside a function. The framework needs the publisher returned by the function to coordinate lifecycle, errors, and completion signals. Return the publisher:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> process() {
    return events -> events.map(this::handle);
}
```

If the function must call a blocking service, wrap the call in `Mono.fromCallable()` and attach a scheduler as shown in earlier examples.

### Using parallel for Blocking I/O

`Schedulers.parallel()` is designed for CPU-bound work. Calling JDBC or blocking HTTP on this scheduler can occupy workers meant for computation and slow down other pipelines. Move blocking calls to bounded elastic or a dedicated blocking scheduler.

### Shifting the Entire Pipeline to boundedElastic

There is no need to push every operator onto bounded elastic. Lightweight transformations and reactive clients can continue running on the current scheduler. Switch only the exact segment performing blocking operations or needing thread isolation.

## 11. Errors and Cancellation Across Scheduler Switches

When an inner publisher fails, the error propagates via reactive signals to downstream unless handled or transformed into another value. For Spring Cloud Stream reactive functions, keep errors represented in the publisher so the framework/binder applies the configured error-handling policy. Do not swallow exceptions inside lambdas and return fake results.

Cancellation can occur when downstream cancels the subscription, times out, or the application shuts down. Reactor can cancel tasks to the extent supported by the scheduler and source. However, a blocking call executing inside a library that does not support interruption/cancellation may keep running until the library returns or times out. Therefore:

- Configure connect/read/request timeouts in blocking clients.
- Avoid calling libraries with unbounded wait times.
- Place timeouts at the appropriate layer and recognize that a reactive timeout does not necessarily halt in-flight blocking I/O.
- Ensure retryable operations are idempotent if prior outcomes are uncertain.
- Track in-flight tasks during application shutdown.

A scheduler only decides where execution runs; it does not automatically guarantee a blocking call stops immediately upon subscription cancellation.

## 12. Testing Blocking Call Isolation

Test both business results and how the pipeline handles errors. Example with `StepVerifier`:

```java
@Test
void processesBlockingCallOnBoundedElastic() {
    LegacyInventoryClient client = event -> {
        if (event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        return new Reservation(event.orderId(), true);
    };

    Function<Flux<OrderEvent>, Flux<OrderResult>> function =
        events -> events.flatMap(
            event -> Mono.fromCallable(() -> client.reserve(event))
                .subscribeOn(Schedulers.boundedElastic())
                .map(reservation -> OrderResult.from(event, reservation)),
            4
        );

    StepVerifier.create(
            function.apply(Flux.just(new OrderEvent("order-1001")))
        )
        .expectNextMatches(result ->
            result.orderId().equals("order-1001") && result.reserved())
        .verifyComplete();
}
```

This test verifies the function's output with a synchronous client. To verify thread isolation, you can record the thread name inside a stub and assert the call ran on the selected scheduler; avoid relying on an exact thread name if Reactor versions or pool configurations can change.

Test layers should include:

1. Unit tests for transformations and error handling.
2. Tests confirming blocking stubs execute off the initial orchestration thread.
3. Tests for concurrency bounds and timeouts when downstream is slow.
4. Integration tests with the binder to verify the reactive function is wired properly.
5. Load tests to evaluate queues, latency, connection pools, and behavior when downstream is overloaded.

BlockHound is an optional tool that can detect certain blocking calls on threads marked non-blocking in test environments. It is helpful for catching accidental blocking API calls, though it does not replace integration tests or real load measurements.

## 13. Scheduler Selection Checklist

- Classify the operation as blocking I/O, reactive I/O, or CPU-bound.
- Keep WebClient/R2DBC and non-blocking publishers in the reactive chain; do not offload them without reason.
- Wrap synchronous calls with `Mono.fromCallable()` or `Flux.defer()`.
- Use `subscribeOn(boundedElastic)` for blocking sources; use `publishOn` when shifting downstream segments.
- Use `parallel()` for CPU-bound computations, never for JDBC or blocking HTTP.
- Bound concurrency, timeouts, connection pools, and queues.
- Never call `block()` or manually `subscribe()` inside a reactive function.
- Manage the lifecycle of dedicated schedulers and dispose them on application shutdown.
- Keep errors inside the publisher so the binder/framework can handle them per configured policy.
- Test thread isolation, cancellation, errors, and load in an appropriate environment.

## 14. References

- [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html), sections on `subscribeOn`, `publishOn`, and standard schedulers.
- [Project Reactor API — Schedulers](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html), sections on `boundedElastic`, `parallel`, and creating custom schedulers.
- [Spring Cloud Stream Reference — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html), sections on reactive functions and message integration.

In Spring Cloud Stream, reactive functions enable stream-based message processing and asynchronous composition. To preserve responsiveness, isolate blocking libraries from orchestration threads using bounded elastic or a dedicated scheduler; CPU computations should use parallel. Choosing `subscribeOn` and `publishOn` properly, bounding concurrency, and controlling timeouts keeps the pipeline from blocking message processing when integrating with synchronous systems.

