# `Consumer<Flux<T>>` and the `Function<Flux<T>, Mono<Void>>` Alternative

## Objectives

Spring Cloud Stream supports a reactive function model based on Project Reactor. Instead of receiving individual objects independently, a function can receive an entire `Flux<T>` stream containing multiple messages. For a consumer that only performs side effects, two declaration styles are commonly considered:

- `Consumer<Flux<T>>`: a function that receives a Flux but has a `void` return type.
- `Function<Flux<T>, Mono<Void>>`: a function that receives a Flux and returns a publisher representing when processing completes, without emitting output payloads.

The difference in return type affects how subscriptions, errors, and the processing lifecycle are managed. This lesson explains when each approach fits, how to control sequential vs. parallel execution, how to avoid blocking, and how to test reactive pipelines in a Spring Cloud Stream application.

After this lesson, you will be able to:

- Distinguish a per-message consumer from a consumer receiving a `Flux<T>`.
- Explain why `Consumer<Flux<T>>` must manage its own subscription.
- Use `Function<Flux<T>, Mono<Void>>` to represent processing completion.
- Choose `concatMap`, `flatMap`, or other operators appropriate for ordering and concurrency requirements.
- Handle errors and backpressure without blocking reactive threads.
- Test pipelines and verify semantics with the deployed binder/broker.

## 1. Flux Is a Data Stream, Not a Collection

`Flux<T>` is a Reactor Publisher that can emit zero to many elements over time. It is not equivalent to `List<T>`:

- `List<T>` holds elements already present in memory.
- `Flux<T>` describes a data emission process that can occur asynchronously.
- The subscriber requests data via demand; the publisher can emit gradually according to consumption speed and backpressure support.
- A Flux can complete, emit an error, or remain open indefinitely.

Example of a function receiving individual messages:

```java
public record OrderCreated(String eventId, String orderId) {}

@Bean
Consumer<OrderCreated> orderCreated(OrderService service) {
    return event -> service.handle(event);
}
```

This is the imperative style: each time the function is invoked, it receives one `OrderCreated`. With a reactive consumer, the parameter is the whole stream:

```java
@Bean
Consumer<Flux<OrderCreated>> orderStream(OrderService service) {
    return events -> events
            .doOnNext(event -> service.recordReceived(event.eventId()))
            .subscribe();
}
```

The `Consumer<Flux<OrderCreated>>` signature means the function accepts a Flux, not that it automatically returns a publisher for the framework to track. This is an important distinction when you need to tie processing completion to the message lifecycle.

## 2. Consumer<Flux<T>>: Self-Subscribing Consumer

`Consumer` is a functional interface whose method returns `void`. When using `Consumer<Flux<T>>`, the code receives the Flux and must create a subscription for the pipeline to start running. If you only construct an operator chain without subscribing, the operations will not execute.

Example with asynchronous side effects:

```java
@Bean
Consumer<Flux<OrderCreated>> orderConsumer(OrderService service) {
    return events -> events
            .concatMap(event -> service.handle(event))
            .doOnError(error ->
                    log.error("Order stream failed", error))
            .subscribe();
}
```

Assume `service.handle(event)` returns `Mono<Void>`. `concatMap` invokes handling for each event and waits for the previous event's publisher to complete before moving to the next event.

### Consequences of Manual Subscription

Because `subscribe()` is called inside the Consumer:

- Application code decides when to subscribe.
- The Consumer call can return immediately after creating the subscription while the pipeline keeps running.
- Errors occurring after subscribing do not automatically become synchronous exceptions of the Consumer call.
- The application must consider how to track and manage subscriptions, errors, and shutdown.
- You should not create multiple independent subscriptions on the same input Flux if doing so causes each message to be processed repeatedly.

A common mistake is forgetting `subscribe()`:

```java
@Bean
Consumer<Flux<OrderCreated>> brokenConsumer(OrderService service) {
    return events -> events
            .concatMap(service::handle);
            // Not subscribed: the pipeline is not consumed.
}
```

Another mistake is subscribing multiple times to the same source or creating additional subscriptions inside each processing branch. Depending on the Flux source and binder, this can cause duplicate side effects, resource contention, or unexpected behavior.

### Error Management in a Consumer

You can attach an error callback in the subscription:

```java
@Bean
Consumer<Flux<OrderCreated>> orderConsumer(OrderService service) {
    return events -> events
            .concatMap(service::handle)
            .subscribe(
                    ignored -> { },
                    error -> log.error("Order processing failed", error)
            );
}
```

With `Mono<Void>`, the pipeline emits no `onNext` values, so the value callback is typically never called; the error callback receives the subscription's error signal. The example logs only to illustrate where errors surface. In a real application, logging does not automatically trigger retries, send messages to a DLQ, or ensure the broker knows processing failed. You need an explicit error policy and must verify the binder's ack/nack or offset commit behavior.

Because Consumer returns `void`, the framework receives no publisher representing when the application-subscribed pipeline finishes. Therefore, if the requirement is for the framework to observe completion/error of reactive work, a function returning a publisher usually expresses intent more clearly.

## 3. Function<Flux<T>, Mono<Void>>: Returning a Completion Signal

`Function<Flux<T>, Mono<Void>>` accepts an input stream and returns a `Mono<Void>`. This Mono emits no result payload; it simply represents that processing has completed or failed.

Example:

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processOrders(
        OrderService service) {
    return events -> events
            .concatMap(event -> service.handle(event))
            .then();
}
```

Here:

1. The framework supplies the input Flux to the function.
2. The function builds a pipeline to process each event.
3. `concatMap` invokes `service.handle` sequentially.
4. `then()` converts the result into `Mono<Void>`, emitting a completion signal only when upstream completes.
5. The function returns the publisher for the framework to manage the subscription under the reactive model.

Unlike a Consumer, the function does not call `subscribe()` manually. The framework can observe the returned publisher to manage execution and completion/error signals according to the integration of the version in use.

`Mono<Void>` does not mean an empty message is sent to an output destination. It represents completion without emitting data elements. When using this signature as an input-only endpoint, verify how your Spring Cloud Stream version interprets the `Void` output type and configure bindings accordingly; do not declare a dummy output destination just because the interface is named `Function`.

### Why Use then()?

The `concatMap` chain produces a Flux from the processing publishers. `then()` discards output values and retains only the completion signal:

```java
Mono<Void> completion = events
        .concatMap(service::handle)
        .then();
```

If a `service.handle` call emits an error, that error propagates through the pipeline and the Mono terminates with an error signal rather than completion. This prevents errors from being turned into apparent success simply because a manual subscription was created.

If a business result needs to be emitted, the signature should return a data-bearing type, such as `Function<Flux<OrderCreated>, Flux<OrderAccepted>>` or another appropriate publisher type, instead of `Mono<Void>`.

## 4. Comparing the Two Signatures

| Criterion | `Consumer<Flux<T>>` | `Function<Flux<T>, Mono<Void>>` |
|---|---|---|
| Return type | `void` | Publisher representing completion |
| Subscription | Consumer code typically must call `subscribe()` | Returns publisher for framework management under reactive model |
| Completion tracking | Consumer returns no completion to caller | Completion is carried by `Mono<Void>` |
| Error signal propagation | Post-subscribe errors belong to app-managed subscription | Error signal is carried by the returned publisher |
| Lifecycle management | App must handle subscription and shutdown | Framework can manage subscription per function lifecycle |
| Best suited for | Self-managed reactive consumers or special integrations | Input-only streams needing publisher-based completion signaling |
| Risks | Forgetting to subscribe, errors detached from invocation, duplicate subscriptions | Need to verify function/binder support for Void output semantics |

For message processing where completion/errors should be tied to the framework's pipeline, `Function<Flux<T>, Mono<Void>>` usually expresses intent more cleanly. Still, you cannot infer acknowledgement semantics solely from the Java signature; the specific binder and version still govern how reactive signals map to message delivery.

## 5. Choosing Sequential or Parallel Execution

After choosing a signature, decide how elements inside the Flux should be processed.

### concatMap: Sequential

`concatMap` starts the next publisher only after the current publisher completes. This is appropriate when:

- Events must be applied in receipt order.
- The same aggregate has dependent mutations.
- You want concurrency limited to one.
- You want predictable behavior when debugging.

```java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> processInOrder(
        OrderService service) {
    return events -> events
            .concatMap(service::apply)
            .then();
}
```

Sequential processing across the entire Flux can limit throughput. If ordering is only needed per order ID, design key-based processing and partitioning so different keys are processed in parallel while the same key follows the appropriate order.

### flatMap: Bounded Parallelism

`flatMap` allows multiple inner publishers to run concurrently. It can increase throughput when events are independent, though completion order may differ from input order.

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processConcurrently(
        OrderService service) {
    return events -> events
            .flatMap(service::handle, 8)
            .then();
}
```

The `8` parameter limits how many inner publishers are subscribed concurrently in the example. Choose concurrency based on database/API capacity and downstream limits; increasing this number does not automatically make the broker faster.

### flatMapSequential

`flatMapSequential` can subscribe to and execute inner publishers concurrently while emitting results in source order. It may buffer early-completing results if a preceding publisher is still slow. If inner publishers have external side effects, emitting results in order does not mean the side effects occurred in that order.

Therefore, if side-effect ordering is a business requirement, `concatMap` or key-based partitioning is usually easier to reason about.

## 6. Backpressure and Resource Limits

Backpressure is the mechanism by which a consumer signals how much data it is ready to receive. In Reactor, a subscriber can request a number of elements via demand; operators can also buffer or adjust prefetch.

A well-behaved reactive pipeline should:

- Avoid reading an entire stream into a `List` if data can be large or unbounded.
- Bound concurrency when calling databases or APIs.
- Avoid creating unbounded buffers.
- Never call `block()` inside a reactive chain.
- Use operators suited to the source's throttling capabilities.
- Measure queue depth, latency, throughput, and active subscription counts.

Example limiting concurrent operations:

```java
@Bean
Function<Flux<PaymentCaptured>, Mono<Void>> recordPayments(
        PaymentService service) {
    return events -> events
            .flatMap(service::record, 4)
            .then();
}
```

Reactor backpressure does not mean every broker stops delivering messages strictly according to downstream demand. The binder may have to translate demand into prefetch, polling, pause/resume, or other mechanisms. Throttling capabilities and buffer limits differ across Kafka, RabbitMQ, and Pulsar binders; check documentation and observe runtime behavior.

## 7. Do Not Block Reactive Threads

Do not use blocking operations inside a pipeline such as:

- `block()` or `blockFirst()`.
- `Thread.sleep()`.
- Synchronous JDBC queries on an event loop.
- Synchronous HTTP calls or waiting on a Future via `get()`.
- Converting a Flux into a large collection and processing it synchronously.

If a service uses a reactive database or WebClient, return `Mono`/`Flux` directly so the pipeline can compose:

```java
public Mono<Void> handle(OrderCreated event) {
    return inventoryRepository.reserve(
                    event.orderId(),
                    event.lines()
            )
            .then(outboxRepository.append(
                    StockReserved.from(event)
            ));
}
```

If you must integrate a blocking library, isolate that operation on an appropriate scheduler instead of running it on the event loop:

```java
Mono<Void> handleLegacy(OrderCreated event) {
    return Mono.fromRunnable(() -> legacyService.reserve(event))
            .subscribeOn(Schedulers.boundedElastic())
            .then();
}
```

Do not offload every operation to `boundedElastic` by default. Use it only for genuinely blocking work and control concurrency so you do not exhaust the scheduler.

## 8. Error Handling in a Reactive Pipeline

Reactor represents errors with a terminal signal. When a publisher emits an error, the pipeline normally terminates unless an error-handling operator is present. You can separate transient errors from unrecoverable errors:

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processOrders(
        OrderService service) {
    return events -> events
            .concatMap(event ->
                    service.handle(event)
                            .retryWhen(
                                    Retry.backoff(2, Duration.ofMillis(200))
                                            .filter(this::isTransient)
                            )
            )
            .then();
}
```

The example retries up to two additional times per event handling invocation if the error matches `isTransient`. Retry in Reactor differs from broker redelivery. If the pipeline still fails after retries, the error signal may be routed to Spring Cloud Stream/binder error handling depending on configuration; the binder may ack/nack, commit offsets, redeliver, or route to a DLQ according to its own semantics.

Do not use `onErrorResume(error -> Mono.empty())` to turn every error into completion. That can make the framework perceive the pipeline as successful even though business work was not completed. Recover from an error only when a clear business outcome exists, such as recording a valid rejection state or routing the event to a traceable error store.

When processing a large Flux with `concatMap`, an error on one event can terminate the entire pipeline. If per-event error isolation is needed, you can place recovery inside the inner publisher, while clearly distinguishing errors handled cleanly by business rules from errors needing broker retry/DLQ. Never swallow errors just to keep subsequent messages running.

## 9. Acknowledgement and Delivery Semantics

Reactive completion does not automatically equate to exactly-once delivery. Three layers must be distinguished:

1. **Reactor completion:** the publisher has completed or errored.
2. **Framework processing:** Spring Cloud Stream observes the function's signals and applies the corresponding error-handling mechanism.
3. **Broker delivery state:** the binder acknowledges, commits offsets, nacks, redelivers, or updates subscriptions per broker mechanics.

With a self-subscribing `Consumer<Flux<T>>`, the function returns `void` before the inner pipeline necessarily completes. Therefore, do not assume the framework can wait for every side effect in that subscription to acknowledge messages. Carefully verify ack/error semantics when using this signature.

With `Function<Flux<T>, Mono<Void>>`, completion/errors are expressed in the returned publisher, giving the framework an opportunity to manage the pipeline under reactive integration. However, exact commit/ack timing still depends on the binder, batch/polling behavior, transactions, and version. Verify with integration tests that inject errors at different points.

Regardless of the signature chosen, consumers should be idempotent. An event can be redelivered after a restart, timeout, or failed commit. Use stable event IDs, inbox/unique constraints, or idempotency keys to avoid duplicating business side effects.

## 10. Complete Examples for Both Alternatives

Suppose the service returns `Mono<Void>` once the event has been recorded:

```java
public interface OrderService {
    Mono<Void> handle(OrderCreated event);
}
```

### Option A: Consumer<Flux<T>>

```java
@Bean
Consumer<Flux<OrderCreated>> consumeOrders(OrderService service) {
    return events -> events
            .concatMap(service::handle)
            .doOnError(error ->
                    log.error("Reactive consumer failed", error))
            .subscribe();
}
```

Characteristics:

- Consumer subscribes manually.
- The pipeline can continue running after the Consumer method returns.
- You must decide where to manage errors and subscription lifecycle.
- Cannot rely on Consumer's return value to signal completion.

### Option B: Function<Flux<T>, Mono<Void>>

```java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> processOrders(
        OrderService service) {
    return events -> events
            .concatMap(service::handle)
            .then();
}
```

Characteristics:

- Function returns a completion publisher.
- No manual subscription.
- Completion/errors live inside the reactive chain managed by the framework.
- `Mono<Void>` emits no output messages; verify how the function catalog/binder of your version handles a Void output type.

These two beans are alternatives for the same input flow. Do not declare both consuming the same destination simultaneously unless you intentionally want two independent logical consumers.

## 11. Binding and Function Definition Configuration

Example configuration for a function named `processOrders`:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
```

The input binding name is derived from the function name and input index. If the function produces data output, declare the corresponding output binding. With `Function<Flux<T>, Mono<Void>>`, there is no output payload to send; check your framework version's behavior and do not configure a dummy output destination just to satisfy naming conventions.

Reactive support and how binders wire demand/acknowledgement can differ across binders and Spring Cloud Stream versions. Do not assume a pipeline passing with the Test Binder means every production binder shares the same backpressure or redelivery behavior.

## 12. Testing Reactive Functions

Unit tests for a function returning `Mono<Void>` can use Reactor Test and `StepVerifier`:

```java
@Test
void shouldCompleteAfterAllOrdersAreHandled() {
    OrderService service = event -> Mono.empty();

    Function<Flux<OrderCreated>, Mono<Void>> function =
            events -> events.concatMap(service::handle).then();

    StepVerifier.create(function.apply(Flux.just(
                    new OrderCreated("evt-1", "order-1"),
                    new OrderCreated("evt-2", "order-2")
            )))
            .verifyComplete();
}
```

The test above verifies that the publisher completes after inner publishers complete. Add tests verifying:

- Events are processed in order with `concatMap`.
- `flatMap` does not exceed configured concurrency.
- Service errors propagate as error signals.
- Retries apply only to transient errors.
- Errors are not accidentally turned into completion.
- An empty Flux completes normally if that is the expected semantics.
- Cancel/dispose stops further work to the extent supported by the publisher.

For `Consumer<Flux<T>>`, unit tests need to verify that the subscription actually runs and asynchronous processing finishes. You can use `Sinks.One`, `CountDownLatch` in tests, or test doubles with completion signals; avoid arbitrary sleeps since they produce flaky tests. A self-subscribing Consumer also needs tests for its error callback and subscription teardown.

### Integration Testing with a Binder

Use the Test Binder or a test broker to verify:

- The input binding is created and the function is triggered.
- Payloads are converted to the right type.
- The reactive pipeline receives messages with the expected semantics.
- Errors are handled per retry/error/DLQ configuration.
- Acknowledgements/offsets advance only as expected when the pipeline completes or errors.
- Backpressure, prefetch, or polling behavior matches the real binder.

The Test Binder does not fully simulate Kafka polling/commits, RabbitMQ prefetch/acks, or Pulsar subscription acknowledgements. For production delivery guarantees, run integration tests against the corresponding binder/broker.

## 13. Which Approach Should You Choose?

Use `Consumer<Flux<T>>` when there is a clear reason for the consumer to own its subscription, such as integrating with a specialized reactive source or custom designed lifecycle management. In that case, have a clear strategy for errors, disposal, shutdown, and delivery semantics.

Use `Function<Flux<T>, Mono<Void>>` when you want to represent an input-only stream that performs side effects and returns a completion signal to the framework. This is usually the cleaner way to express reactive processing where completion/errors stay within the publisher. Verify that this signature is properly supported in your Spring Cloud Function/Spring Cloud Stream version and binder.

If a reactive stream is unnecessary and each message is processed independently, an imperative `Consumer<T>` may be simpler. Do not switch to Flux simply to make code look asynchronous; the reactive model is meaningful when the entire processing path supports non-blocking execution, backpressure, and composition.

## Conclusion

`Consumer<Flux<T>>` receives a stream but returns `void`, so code typically must subscribe and manage the subscription itself. `Function<Flux<T>, Mono<Void>>` returns a publisher representing completion time without emitting output payloads, allowing the framework to manage the reactive pipeline under its integration model.

Choose operators based on ordering and concurrency requirements: `concatMap` for sequential processing, `flatMap` for bounded parallel processing. Avoid blocking, control backpressure, and do not swallow errors. Reactor completion, framework processing, and broker acknowledgement are distinct layers; verify your binder's semantics and always design idempotent consumers to tolerate redelivery.

