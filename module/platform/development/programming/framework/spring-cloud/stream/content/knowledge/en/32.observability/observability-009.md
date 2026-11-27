# Observing Reactive Functions at Element or Stream Scope

In Spring Cloud Stream, a reactive function typically takes `Flux<T>` and returns `Flux<R>` or `Mono<Void>`. Unlike an imperative function, a reactive function is not invoked once per message by the framework. The framework invokes the function once at startup to connect the application-declared stream with the binder's source and target streams. Afterward, Reactor drives subscriptions, signal emission, error handling, and stream completion.

Because reactive functions are not automatically wrapped by Spring Cloud Function with `ObservationFunctionAroundWrapper`, the application must choose the scope to observe. That scope can be a single message, a batch of messages, a processing segment in the pipeline, or the entire subscription of a stream. Reactor provides `tap(Micrometer.observation(registry))` to attach a Micrometer Observation to the chosen segment.

## 1. Why do reactive functions require manual observation?

With an imperative function, the framework receives a message, invokes the function, waits for the result, and finishes one invocation. An Observation can wrap each call, so each message generally maps to one Observation.

Reactive functions follow a different lifecycle:

1. Spring Cloud Stream calls the function at startup to obtain a declared `Flux`/`Mono`.
2. The binder connects the source publisher to the target publisher.
3. Once wired, Reactor manages data processing.
4. A single subscription can receive many messages over a long period, or even never complete.

Consequently, there is no per-message function invocation for the framework to wrap automatically. If you only add tracing dependencies and expect the framework to create spans per event, you may not get the observation scope you want. You must place Observations inside the reactive pipeline.

| Model | How the function is called | Default Observation scope |
|---|---|---|
| Imperative `Function<T, R>` | Once per message | One Observation per invocation when observability infra is present |
| Reactive `Function<Flux<T>, Flux<R>>` | Once when assembling the pipeline | No automatic per-element Observation |
| Reactive with `tap` inside `Mono` per element | Pipeline assembled once; each element creates a Mono | One Observation per processed message |
| Reactive with `tap` on a `Flux` | Pipeline assembled once; Observation bound to that Flux segment's subscription | One Observation for the entire subscription/stream segment |

## 2. Observation, metrics, and traces

Micrometer Observation is the common abstraction for recording an application activity. Depending on configured ObservationHandlers and tracer bridges, an Observation can emit metrics, trace spans, or both.

In a Spring Boot application, baseline dependencies typically include:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-core-micrometer</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

This example uses the OpenTelemetry bridge. You can pick another tracer bridge supported by Spring Boot; to export traces to a specific backend, add the matching exporter/registry. Let Spring Boot dependency management control versions rather than picking standalone versions piecemeal.

Spring Boot configures `ObservationRegistry` when suitable observability dependencies are present. You can inject the registry into the function bean:

~~~java
@Bean
Function<Flux<String>, Flux<String>> processOrders(
        ObservationRegistry observationRegistry) {
    return events -> events
        .map(String::toUpperCase)
        .name("orders.normalize")
        .tap(Micrometer.observation(observationRegistry));
}
~~~

`ObservationRegistry` is the sink for Observations. `tap` is the point in the Reactor pipeline that creates and manages the Observation for the subscription. Simply injecting the registry without attaching `tap` does not specify which reactive segment to measure.

## 3. `tap` defines the unit of observation

Reactor's `tap` accepts a `SignalListener` or a listener created by an integration library. With Micrometer, use:

~~~java
.tap(Micrometer.observation(observationRegistry))
~~~

The Observation is attached to the publisher where `tap` is placed. Duration is measured from subscription start until that publisher segment completes, errors, or is cancelled. Therefore, the placement of `tap` determines the scope:

- Placed on a `Mono` created per event: observes each event.
- Placed on a `Mono` created per batch: observes each batch.
- Placed on a bounded `Flux`: observes that stream segment.
- Placed on a long-lived consumer `Flux`: the Observation may stay open until the subscription is cancelled or terminates.

There is no single default choice fitting every reactive function. Decide upfront which operational question you want to answer: how long does one message take, how long does one batch take, or how is the overall pipeline behaving?

## 4. Observing each message with `Mono`

If you want each message to have its own Observation, create a `Mono` publisher per element and place `tap` on that publisher:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> observeEachOrder(
        ObservationRegistry observationRegistry) {

    return events -> events.flatMap(event ->
        Mono.just(event)
            .map(this::normalize)
            .flatMap(this::enrich)
            .name("orders.process")
            .tap(Micrometer.observation(observationRegistry))
    );
}
~~~

Here, each time `flatMap` receives an `OrderEvent`, it creates a `Mono` representing the processing of that event. The Observation begins when the Mono is subscribed to and ends when the event's processing chain completes, errors, or is cancelled. If `enrich` is an asynchronous operation returning `Mono<OrderResult>`, the Observation includes waiting for that publisher to finish.

The name `orders.process` is stable and describes the operation. Never name it after `eventId`, `orderId`, or per-message dynamic values, as Observation names typically form part of metric identity and can cause huge cardinality.

`flatMap` can process multiple events concurrently. Each inner `Mono` still gets its own Observation. If input ordering must be preserved, consider `concatMap`; choosing `flatMap`, `concatMap`, or concurrency limits is a stream-processing decision, not an Observation setting.

## 5. Observing a batch or bounded segment

A single message is not always the right unit. A pipeline may group multiple events and process them as a batch. You can use `bufferTimeout` to form batches by count or duration:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<BatchResult>> observeOrderBatches(
        ObservationRegistry observationRegistry) {

    return events -> events
        .bufferTimeout(100, Duration.ofSeconds(1))
        .filter(batch -> !batch.isEmpty())
        .flatMap(batch ->
            Mono.fromSupplier(() -> aggregate(batch))
                .name("orders.batch")
                .tap(Micrometer.observation(observationRegistry))
                .flux()
        );
}
~~~

Each batch creates a `Mono`, so each batch execution gets one Observation. This example collects up to 100 events or emits a batch after waiting one second. That changes pipeline semantics: it affects latency, memory, and emission timing. Only use batching if business requirements allow it.

A bounded processing segment can also be observed directly:

~~~java
Flux<OrderResult> normalizedSegment = events
    .map(this::normalize)
    .filter(this::isValid)
    .name("orders.normalize.segment")
    .tap(Micrometer.observation(observationRegistry));
~~~

In this example, the Observation measures the subscription of the combined `normalize` and `filter` segment, not one Observation per element. If upstream is a continuous consumer stream, the Flux segment may not complete for a long time. In that case, the segment's timer will only stop upon complete, error, or cancellation; its duration cannot be interpreted as single-message latency.

## 6. Observing the whole stream subscription

You can place `tap` across the entire pipeline when you want to track the lifetime, termination outcome, and state of a subscription:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> observeWholeStream(
        ObservationRegistry observationRegistry) {

    return events -> events
        .map(this::normalize)
        .filter(this::isValid)
        .flatMap(this::enrich)
        .name("orders.stream")
        .tap(Micrometer.observation(observationRegistry))
        .map(this::toResult);
}
~~~

The Observation wraps the publisher chain preceding `tap`; operators placed after `tap` fall outside the measured segment. If you also want to measure `toResult`, move `tap` below that operator.

A Kafka consumer usually creates a long-lived subscription. Observing the entire subscription as a single Observation can keep a span/timer open for hours or days. While useful for certain stream lifecycle signals, it does not replace message latency. For continuous consumers, it is usually better to have per-event or per-batch Observations alongside separate metrics for throughput, backlog, and consumer state.

## 7. Comparing observation scopes

| Scope | How `tap` is placed | One Observation represents | When to use |
|---|---|---|---|
| One message | Inside `flatMap`, on an inner `Mono` | One event processing execution | Measuring per-event latency and errors |
| One batch | Inside batch `flatMap`, on an inner `Mono` | One batch execution | Measuring aggregation/bulk write time |
| A bounded segment | On a bounded `Flux` | One subscription of that segment | Measuring a finite pipeline stage |
| Whole stream | On a long-lived publisher | Subscription lifetime | Tracking stream lifetime or status |

When choosing a scope, define clearly where the Observation starts and ends. If you need to measure broker wait time, you need instrumentation at the corresponding binder/producer/consumer layer; `tap` inside a function only measures the reactive pipeline segment it wraps.

## 8. Naming Observations and adding metadata

Reactor lets you name a sequence with `name(String)`. With an Observation tap, that name identifies the Observation. Choose stable operation-based names:

~~~java
events
    .map(this::validate)
    .name("orders.validate")
    .tap(Micrometer.observation(observationRegistry));
~~~

If custom metadata is needed, supply an Observation supplier:

~~~java
events.flatMap(event ->
    Mono.just(event)
        .flatMap(this::enrich)
        .tap(Micrometer.observation(
            observationRegistry,
            registry -> Observation.createNotStarted(
                    "orders.enrich",
                    registry
                )
                .lowCardinalityKeyValue("stage", "enrich")
                .highCardinalityKeyValue("event.id", event.eventId())
        ))
);
~~~

`lowCardinalityKeyValue` fits attributes with a small, stable value set, such as `stage=validate` or `result=accepted`. These values can enter metrics. `highCardinalityKeyValue` is meant for values that vary widely, such as event IDs; they fit traces better and should not become metric labels.

Never put `orderId`, `customerId`, emails, tokens, or sensitive payloads into low-cardinality tags. High-cardinality trace attributes can also expose personal data or secrets; add only approved data genuinely needed for investigation.

## 9. Placement of `tap` relative to retry

The position of `tap` relative to `retryWhen` determines whether an Observation represents a single attempt or the entire logical operation.

**One Observation per attempt:**

~~~java
Mono.just(event)
    .flatMap(this::callRemoteService)
    .name("orders.remote.attempt")
    .tap(Micrometer.observation(observationRegistry))
    .retryWhen(retryPolicy);
~~~

`retryWhen` re-subscribes to the upstream publisher. Since `tap` sits before `retryWhen`, each attempt creates a separate subscription/Observation. This is useful when measuring attempt counts and per-attempt latency.

**One Observation for the whole operation, including retries:**

~~~java
Mono.just(event)
    .flatMap(this::callRemoteService)
    .retryWhen(retryPolicy)
    .name("orders.remote.operation")
    .tap(Micrometer.observation(observationRegistry));
~~~

Here, `tap` sits after retry. It observes the final result of the publisher once retries conclude, so duration includes all attempts and backoff delays. If a retry succeeds, the operation Observation can finish as a success even though prior attempts failed. If you need both views, place an inner Observation for attempts and an outer Observation for the operation with distinct names.

## 10. Placement of `tap` relative to error handling

`onErrorResume` can turn an error into a fallback result. The position of `tap` decides whether the Observation sees the original error or the recovered outcome:

~~~java
Mono.just(event)
    .flatMap(this::enrich)
    .name("orders.enrich")
    .tap(Micrometer.observation(observationRegistry))
    .onErrorResume(this::fallbackResult);
~~~

Because `tap` sits before `onErrorResume`, the Observation sees the error signal from `enrich`. Only afterward does the pipeline turn the error into a fallback result.

If `tap` is moved below `onErrorResume`, the Observation sees the recovered publisher and may record completion instead of an error:

~~~java
Mono.just(event)
    .flatMap(this::enrich)
    .onErrorResume(this::fallbackResult)
    .name("orders.enrich.with-fallback")
    .tap(Micrometer.observation(observationRegistry));
~~~

Choose based on the question you need to answer. If you need the technical failure rate of the enrich step, place Observation before recovery. If you need the final outcome delivered downstream, place Observation after recovery. Do not use fallback to hide errors when the system still needs to alert on or record the underlying failure.

## 11. Context propagation in reactive pipelines

Trace context and related metadata typically travel via Reactor Context. When a pipeline switches threads via `publishOn`, `subscribeOn`, or external library callbacks, ensure context propagation is configured appropriately so trace/span and logging context are not lost.

Example enabling automatic context propagation at startup:

~~~java
public static void main(String[] args) {
    Hooks.enableAutomaticContextPropagation();
    SpringApplication.run(OrdersStreamApplication.class, args);
}
~~~

This hook helps propagate context across supported Reactor processing boundaries. It does not automatically create Observations for reactive functions; you still need `tap`. If your application uses Spring Boot/Reactor with property-based context propagation, use one consistent mechanism for your running version and avoid enabling overlapping mechanisms unnecessarily.

Never propagate trace IDs by manually stuffing them into the business payload if the goal is merely tracing. Use Observation/Micrometer context and framework propagation mechanisms; only put business correlation IDs in headers when they are part of the message contract.

## 12. Metrics generated from Observation tap

Reactor Micrometer Observation tap can generate timers for sequence duration and long-task timers for active sequences. Termination statuses are typically distinguished as:

| Status | Meaning |
|---|---|
| `completed` | Sequence emitted at least one element and completed |
| `completedEmpty` | Sequence completed without emitting any elements |
| `error` | Sequence terminated with an error |
| `cancelled` | Subscription was cancelled |

These statuses are helpful when reading metrics: a consumer may be cancelled due to shutdown/rebalance, a filter may produce an empty sequence, or processing may terminate with an exception. Do not lump cancellation into business errors when cancellation is simply normal lifecycle behavior.

The sequence name set via `name` becomes the Observation's prefix/identity. Keep the number of names finite and meaningful. Avoid generating different names per event, tenant, or request.

## 13. Segment metrics and element metrics are not the same

If `tap` is placed on a long-lived `Flux`, subscriptions are few while lifetimes are very long. If placed on an inner `Mono` per event, Observation count scales with event count. The two approaches answer different questions:

- Stream Observation: is the subscription still active, has it ended, and how long was its lifecycle duration?
- Element Observation: how long did each event take to process, and how many events failed?
- Batch Observation: how long did each batch take, and what are batch size and bulk-operation efficiency?

Never use stream-level duration as message p95/p99 latency. Also avoid generating traces for every single event with unbounded metadata if traffic is very high and trace costs exceed budget. Use sampling for traces and low-cardinality metrics to monitor overall traffic trends.

## 14. Reactive functions and non-reactive binders

Using `Flux`/`Mono` in a function does not automatically mean both source and target support reactive transport. Some binders, such as the regular Kafka Binder or Rabbit binder, may pull messages imperatively and bridge them into the reactive API. In that case, the application can still use Reactor operators and attach Observations to the pipeline, but should not assume end-to-end backpressure or all reactive transport characteristics are supported.

The Reactive Kafka binder has more reactive source/sink integration and its own capabilities. Regardless of the binder, an Observation attached via `tap` only measures the instrumented pipeline segment; to measure publish/receive at the broker layer, enable binder observability or use the corresponding broker/client metrics.

## 15. Reactive Consumers should have a return type expressing completion

For a reactive consumer, `Consumer<Flux<T>>` has a `void` return type, leaving the framework with no returned publisher to subscribe to. When a reactive consumer is needed, `Function<Flux<T>, Mono<Void>>` is generally preferred:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> consumeOrders(
        ObservationRegistry observationRegistry) {

    return events -> events
        .flatMap(event ->
            Mono.just(event)
                .flatMap(this::persist)
                .name("orders.persist")
                .tap(Micrometer.observation(observationRegistry))
        )
        .then();
}
~~~

`then()` produces a `Mono<Void>` that completes when preceding processing completes. If you still use `Consumer<Flux<T>>`, the application itself must subscribe to the Flux because `Consumer` returns no publisher for the framework to subscribe to. Create only one intentional subscription; duplicate subscriptions can spawn multiple processing streams, complicate lifecycle control, or decouple acknowledgments from intended completion.

## 16. Testing Observation scopes

Testing reactive functions should verify both data and Observation lifecycle:

1. Use `StepVerifier` to emit one or more events and assert outputs.
2. Use an `ObservationRegistry` with a test handler to record started/stopped Observations.
3. For a per-item design, send N events and verify N Observations matching the subscribed Mono publishers.
4. For a per-batch design, send enough events to form batches and verify one Observation per batch.
5. For stream-level, verify the Observation only ends when the sequence completes, errors, or cancels.
6. Test errors and cancellations to confirm Observation statuses match expectations.
7. Test retries with `tap` before/after retry to confirm Observation counts match intent.
8. Test context propagation when the pipeline uses `publishOn` or `subscribeOn`.
9. Verify metric labels only use values with appropriate cardinality.

Example testing data behavior:

~~~java
StepVerifier.create(processOrders(inputEvents))
    .expectNextMatches(result ->
        result.orderId().equals("order-1"))
    .verifyComplete();
~~~

This tests reactive output. It does not replace testing Observation handlers or integration testing with a tracing backend; to verify traces appear in the backend, run with exporter configuration and confirm traces are exported successfully.

## 17. Common observation mistakes

| Symptom | Possible cause | How to resolve |
|---|---|---|
| No per-message spans | Only injected ObservationRegistry without placing `tap` in the pipeline | Create per-item Observations with an inner Mono |
| Only one very long Observation appears | `tap` placed on a long-lived consumer Flux | Choose per-item or per-batch when latency is needed |
| Observation never finishes | Sequence never completes and subscription is never cancelled | Revisit observation unit; use a bounded segment |
| Retry shows only one Observation | `tap` placed after `retryWhen` | Place tap before retry if one Observation per attempt is desired |
| Errors do not appear in Observation | `onErrorResume` runs before tap | Place tap before recovery to capture original errors |
| Trace context lost across thread switches | Context propagation not configured properly | Check Reactor Context and automatic propagation |
| Metrics have too many time series | Event ID/order ID used as metric tag or name | Move identifying data to controlled traces/logs |
| Traces missing in backend | Missing tracer bridge/exporter or unconfigured exporter | Check dependencies, ObservationHandler, and exporter |
| Backpressure does not behave as expected | Binder source/target is not a reactive transport | Verify capabilities of the binder in use |

## 18. Implementation checklist

- [ ] Added Actuator, `reactor-core-micrometer`, and required tracer bridge/registry.
- [ ] Confirmed Spring Boot provides `ObservationRegistry`.
- [ ] Accounted for reactive functions being called once to wire the pipeline and not auto-wrapped per message.
- [ ] Chosen the Observation unit: one message, one batch, one segment, or whole subscription.
- [ ] Placed `tap(Micrometer.observation(registry))` at the right position in the pipeline.
- [ ] Assigned stable Observation names via `name`.
- [ ] Decided whether Observations include or separate retry attempts.
- [ ] Placed tap before/after error recovery based on desired semantics.
- [ ] Configured context propagation if the pipeline switches threads and needs trace context preserved.
- [ ] Kept metric tags low-cardinality; excluded personal/business IDs from metric labels.
- [ ] Accounted for trace cost and sampling against actual traffic.
- [ ] Distinguished pipeline Observations from broker-layer metrics/observability.
- [ ] Tested completion, error, cancellation, retry, and context propagation.

Reactive functions do not have one invocation per message, so the framework cannot choose the Observation unit on the application's behalf. Use `tap(Micrometer.observation(registry))` to attach Observations to a clearly scoped publisher segment: an inner `Mono` per event, a `Mono` per batch, or a `Flux` for a segment/subscription. Where tap sits relative to retry and error recovery determines the recorded duration and status. Combined with stable names, controlled cardinality, and proper context propagation, metrics and traces will accurately reflect the processing unit operations teams need to monitor.

## References

- [Spring Cloud Stream — Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream — Reactive Functions](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — Exposing Reactor Metrics and Micrometer Observation](https://projectreactor.io/docs/core/release/reference/metrics.html)
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
