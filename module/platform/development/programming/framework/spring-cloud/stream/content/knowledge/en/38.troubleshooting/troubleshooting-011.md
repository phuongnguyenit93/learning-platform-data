# Reactive Pipeline Stops Processing or Has No Subscriber

A Spring Cloud Stream application may run normally and connect to Kafka/RabbitMQ/Pulsar without errors, yet still **process zero messages**. A frequent cause is building a Reactor operator chain (`Flux` or `Mono`) with no subscriber. In other scenarios, the pipeline had a subscriber that emitted `onError` and terminated, the `Flux` source emitted `onComplete`, the subscription was canceled, or the broker stopped supplying messages. All of these look identical on the surface: business processing logs vanish and backlogs climb.

In Spring Cloud Stream, clearly distinguish a reactive **Function** from a reactive **Consumer**. With `Function<Flux<T>, Flux<R>>`, the framework takes the returned Publisher and wires it to the output binding; the application normally should not call `subscribe()` inside the function. By contrast, `Consumer<Flux<T>>` returns `void`, leaving the framework no resulting Publisher to subscribe to on your behalf; if you choose that signature, you must establish the subscription and manage its lifecycle yourself. Spring Cloud Stream recommends considering `Function<Flux<T>, Mono<Void>>` as a reactive sink when no outbound events are needed.

This lesson belongs to the **Troubleshooting** chapter of the SPRING_CLOUD_STREAM module and applies to event-driven applications built with `Supplier`/`Function`/`Consumer` using Kafka, RabbitMQ, or Pulsar bindings/binders. Examples use Project Reactor and the Spring Cloud Stream 5.1 functional model; verify support and property names for your actual binder and version in production.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **assembly**, **subscription**, **request**, **onNext**, **onError**, **onComplete**, and **cancel** in Reactor.
- Identify `map`/`flatMap`/`doOnNext` chains that are declared but never subscribed to.
- Compare `Function<Flux, Flux>`, `Consumer<Flux>`, and `Function<Flux, Mono<Void>>`.
- Detect when a publisher has completed, been canceled, or terminated with an error.
- Verify that a function bean is actually bound via `spring.cloud.function.definition`.
- Distinguish the regular Kafka binder from the Kafka Reactive Binder and backpressure limits.
- Avoid stray `subscribe()` calls, `block()` on the wrong thread, and retries that kill subscriptions.
- Choose appropriate `onErrorResume`/`retryWhen`, DLQ/quarantine, and acknowledgment strategies.
- Use Reactor diagnostics, Micrometer/Actuator, `StepVerifier`, and broker metrics to investigate.
- Build a runbook to recover pipelines safely without losing or duplicating messages.

## 1. Identify the Symptom Before Changing Code

Not every silent pipeline lacks a subscriber. Classify from observable signals:

| Symptom | Primary Possibility | First Verification Step |
|---|---|---|
| Bean creation log appears, but no per-event logs | Not subscribed; function unbound; empty topic | Check binding and `doOnSubscribe` |
| `onSubscribe` logs appear, but no `onNext` | No data; zero demand; paused source | Check request, assignment, lag/queue depth |
| Processes a few events then stops completely | `onError`, `onComplete`, or `cancel` | Add `doOnError`/`doFinally`; check terminal signal |
| Consumer group has lag while app stays healthy | Subscriber lost, slow handler, or unassigned partitions | Check subscription and Kafka group assignment |
| Input has events while output topic stays empty | Output unsubscribed/unbound; filter dropped items; send failed | Check `Function` output binding, `filter`, and producer errors |
| Events arrive only after deploy/restart | Shared/hot source started before subscriber; lifecycle race | Check cold vs hot source and subscription timing |
| High CPU, zero forward progress | `block()`, locks, blocking I/O, scheduler starvation | Inspect thread dumps and Reactor schedulers |
| DLQ grows, main flow stalls | Poison message / retries exhausted | Inspect error path and broker semantics |

Triage should answer in order: **does the broker have input → is the binding wired right → is there a subscription → is there request/demand → is `onNext` firing → where did it terminate → what happened to offsets/acks?**

## 2. A Publisher Does Not Run Just Because It Was Assembled

Project Reactor implements the Reactive Streams Publisher/Subscriber model. Operators like `map`, `filter`, `flatMap`, or `doOnNext` describe an execution plan. For most cold sources, actual work begins only when a Subscriber subscribes to the Publisher.

~~~java
Flux<String> pipeline = Flux.just("order-1", "order-2")
        .map(String::toUpperCase)
        .doOnNext(value -> log.info("processed {}", value));

log.info("pipeline assembled");
// No subscribe => values from Flux.just are never processed.
~~~

The snippet above only assembles the pipeline. It does not actively publish messages to Kafka, creates no subscriber, and is not how to write a Spring Cloud Stream Function.

For illustration in a **standalone Reactor test program**:

~~~java
pipeline.subscribe(
        value -> log.info("received {}", value),
        error -> log.error("pipeline failed", error),
        () -> log.info("pipeline completed"));
~~~

When implementing `Function<Flux, Flux>` in Spring Cloud Stream, **do not insert this `subscribe()` call inside the function**. The framework needs to own the returned Publisher to connect it to the output binding and manage its lifecycle.

### 2.1. Six Critical Signals

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Subscriber
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(n)
    P-->>S: onNext(event 1)
    P-->>S: onNext(event 2)
    alt Out of data
        P-->>S: onComplete()
    else Unhandled error
        P-->>S: onError(error)
    else Processing canceled
        S->>P: cancel()
    end
~~~

`onComplete` and `onError` are the two terminal signals of a subscription; `cancel` is a Subscriber action stopping the stream via cancellation. After any terminal signal, that subscription never emits `onNext` again. For long-lived broker sources, an entire subscription terminating unexpectedly always warrants investigation.

### 2.2. `map` and `doOnNext` Are Not Subscriptions

~~~java
// Wrong on its own: creates a publisher without executing it.
Flux<String> ignored = source
        .doOnNext(log::info)
        .map(String::toUpperCase);
~~~

`doOnNext` merely peeks at passing signals. It does not replace a terminal subscriber and does not guarantee side effects ever run. In Spring Cloud Stream apps, the Publisher must be returned to the framework or subscribed to responsibly by a consumer.

### 2.3. Cold vs. Hot Sources

A **Cold Publisher** (e.g., `Flux.defer`, `Flux.just`) typically creates a sequence per subscription; a new subscribe can re-run the pipeline. A **Hot Publisher** (e.g., a continuously emitting `Sinks.Many`) can emit data before subscribers arrive; late subscribers may miss events depending on sink type and replay/buffering policy.

| Source | If Subscriber Arrives Late | Notes |
|---|---|---|
| `Flux.just` | Receives full dataset upon subscribing | Finite; completes quickly |
| `Flux.defer` | Creates publisher per subscription | Side effects may re-run |
| `Sinks.Many` multicast | May drop or reject emits with no subscribers, depending on sink | Monitor `EmitResult` |
| `replay()` / replay sink | Can replay buffered history per config | Bound memory and retention |
| Broker consumer flux | Fetches data per binder and broker mechanics | Acks/offsets differ from in-memory replay |

Never "fix" a missing subscriber by sprinkling `share()` or `cache()`. Those operators alter lifetime and replay semantics, risking late-subscriber data loss or memory pressure.

## 3. How Spring Cloud Stream Invokes a Reactive Function

An imperative function:

~~~java
@Bean
Function<String, String> upperCase() {
    return value -> value.toUpperCase(Locale.ROOT);
}
~~~

is normally invoked by the framework **once per message**. A reactive function, by contrast, is typically invoked at pipeline wiring time to obtain the Publisher:

~~~java
@Bean
Function<Flux<String>, Flux<String>> upperCase() {
    return inbound -> inbound
            .map(value -> value.toUpperCase(Locale.ROOT))
            .doOnSubscribe(s -> log.info("reactive processing subscribed"))
            .doOnNext(value -> log.debug("transformed item"));
}
~~~

For a reactive function, the `inbound -> ...` lambda is normally invoked **once to assemble the Flux chain**; that does not mean it processes only one event. Each message flows through the operators once the framework connects and subscribes to the Publisher.

### 3.1. Standard Binding Configuration

~~~yaml
spring:
  cloud:
    function:
      definition: upperCase
    stream:
      bindings:
        upperCase-in-0:
          destination: raw.events
          group: uppercase-processors
        upperCase-out-0:
          destination: normalized.events
~~~

The names `upperCase-in-0` and `upperCase-out-0` derive from the function bean name. Configuration names must match exactly. When an app has multiple functions, declare `spring.cloud.function.definition` so the framework binds the right one. Declaring a bean without activating it in `definition` proves nothing about broker wiring.

### 3.2. Returning a Publisher While Adding a Side `subscribe()`

~~~java
// Anti-pattern: creates a detached subscription and returns a different Flux.
@Bean
Function<Flux<String>, Flux<String>> badFunction() {
    return inbound -> {
        inbound.map(this::expensiveOperation).subscribe();
        return inbound;
    };
}
~~~

This creates an "out-of-band" subscription whose side effects live outside the returned Publisher. It can consume the source twice, duplicate work, bypass output/error handling, or leak unmanaged subscriptions without lifecycle cleanup. Express all processing inside the **returned** Publisher:

~~~java
@Bean
Function<Flux<String>, Flux<String>> goodFunction() {
    return inbound -> inbound
            .map(this::expensiveOperation)
            .doOnError(error -> log.error("processing failed", error));
}
~~~

If `expensiveOperation` performs blocking I/O, do not call it directly inside `map` on a reactive thread; the scheduler section covers how to handle that.

## 4. `Consumer<Flux<T>>`: The Classic Cause of a Missing Subscriber

`Consumer<Flux<T>>` returns `void`. The framework receives no Publisher from `accept(flux)` to subscribe to. Thus a reactive consumer that builds a pipeline and ignores it **processes zero messages**.

### 4.1. Broken Example: Assembling Without Subscribing

Putting operators inside a Consumer body does not execute them:

~~~java
@Bean
Consumer<Flux<OrderCreated>> brokenSink() {
    return input -> {
        Flux<OrderCreated> unused = input
                .map(order -> {
                    log.info("would process {}", order.orderId());
                    return order;
                });
        // Nothing done with unused.
    };
}
~~~

The bean may be invoked to wire the flow, yet without a subscriber, mappers and repositories never run.

### 4.2. Preferred Pattern: `Function<Flux<T>, Mono<Void>>`

Spring Cloud Stream docs recommend `Function<Flux<T>, Mono<Void>>` for reactive sinks. When the function **returns** `Mono<Void>`, the framework receives a Publisher it can subscribe to:

~~~java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> persistOrders(OrderService service) {
    return input -> input
            .concatMap(service::saveReactively)
            .doOnSubscribe(s -> log.info("persistOrders subscribed"))
            .doOnError(error -> log.error("persistOrders failed", error))
            .doFinally(signal -> log.warn(
                    "persistOrders terminated: {}", signal))
            .then();
}
~~~

Assume `OrderService.saveReactively(OrderCreated)` returns `Mono<Void>` and completes **after data is durably persisted**. `concatMap` enforces sequential processing (fitting ordered workflows), while `then()` produces a Mono that terminates when the input completes without emitting payloads.

Example sink binding:

~~~yaml
spring:
  cloud:
    function:
      definition: persistOrders
    stream:
      bindings:
        persistOrders-in-0:
          destination: orders.created
          group: order-persistence
~~~

This is the framework-recommended signature to prevent dropped subscriptions. If your binder version requires explicit offset/ack handling, configure and test it per broker; having a subscriber does **not** guarantee at-least-once delivery by itself.

### 4.3. If `Consumer<Flux<T>>` Is Strictly Required

When an API or lifecycle forces a reactive Consumer, subscribe once and manage the `Disposable`:

~~~java
@Component
class OrderSinkSubscription {
    private final AtomicReference<Disposable> current =
            new AtomicReference<>();

    Consumer<Flux<OrderCreated>> consumer(OrderService service) {
        return input -> {
            Disposable subscription = input
                    .concatMap(service::saveReactively)
                    .doOnSubscribe(s -> log.info("sink subscribed"))
                    .doOnError(e -> log.error("sink terminated", e))
                    .doFinally(s -> log.info("sink finished: {}", s))
                    .subscribe(
                            ignored -> { },
                            error -> log.error("terminal error", error));
            Disposable previous = current.getAndSet(subscription);
            if (previous != null) {
                previous.dispose();
            }
        };
    }

    @PreDestroy
    void close() {
        Disposable subscription = current.getAndSet(null);
        if (subscription != null) {
            subscription.dispose();
        }
    }
}

@Configuration
class SinkConfiguration {
    @Bean
    Consumer<Flux<OrderCreated>> orderSink(
            OrderSinkSubscription subscription,
            OrderService service) {
        return subscription.consumer(service);
    }
}
~~~

This shows explicit subscription ownership and cleanup. Note that `dispose()` triggers cancellation without waiting for in-flight async work to finish. In production, design graceful shutdown/draining, coordinate offsets/acks, and verify the publisher handles cancellation cleanly. Never call `subscribe()` multiple times on the same inbound Flux or per message when one subscription is intended.

**Never use `subscribe()` as the default fix for every reactive pipeline.** For a reactive `Function`, it is usually an anti-pattern; for an explicit reactive `Consumer`, it is the application's responsibility.

## 5. Functional Composition Can Turn a Function into a Consumer

Spring Cloud Function supports composition, e.g.:

~~~properties
spring.cloud.function.definition=transform|sink
~~~

Composing a reactive Function with an imperative Consumer can yield a reactive Consumer returning `void`. The framework then cannot obtain a final Publisher to subscribe to. Thus a pipeline that worked standalone can go silent once a trailing consumer is appended.

Check:

1. Actual Java type of each bean: `Function<Flux<A>, Flux<B>>` or `Consumer<B>`?
2. Resulting composed type: Function, Consumer, or Supplier?
3. Is a terminal Subscriber created with the right lifecycle?
4. Can the final consumer become reactive logic inside `Function<Flux, Mono<Void>>`?
5. If not, would an imperative per-message model be easier to manage?

Never judge solely by `spring.cloud.function.definition`; a syntactically valid composition can still leave the tail unsubscribed.

## 6. Distinguish `onComplete`, `onError`, and `cancel`

All three stop the pipeline from processing further data, yet recovery differs for each.

### 6.1. `onComplete`: A Finite Source Finished

~~~java
@Bean
Supplier<Flux<String>> sampleSupplier() {
    return () -> Flux.just("a", "b", "c");
}
~~~

This is a **finite** reactive Supplier. In Spring Cloud Stream, a reactive Supplier is normally initialized/invoked once to provide the stream. After three items, the source completes. It does not automatically "come back to life" every second like a polled imperative Supplier.

If the goal is periodically emitting a finite dataset, use `@PollableBean` per Spring Cloud Function docs:

~~~java
@PollableBean(splittable = true)
Supplier<Flux<String>> pollSomeRecords() {
    return () -> Flux.just("a", "b", "c");
}
~~~

This tells the framework the Supplier is finite and may need polling. Do not use a finite `Flux` as an infinite stream and then assume the pipeline broke when `onComplete` fires.

### 6.2. `onError`: An Exception Terminated the Stream

~~~java
Flux<String> values = Flux.just("ok", "bad", "later");

values.map(value -> {
    if (value.equals("bad")) {
        throw new IllegalStateException("unexpected data");
    }
    return value;
}).subscribe(
        value -> log.info("next {}", value),
        error -> log.error("terminated", error));
~~~

Upon hitting `bad`, the stream emits `onError` and terminates. `later` is never processed in that subscription. For a long-running broker input function, an unhandled error destroys the subscriber; as the broker keeps receiving messages, lag climbs.

### 6.3. `cancel`: The Subscriber Canceled

Cancellation can come from `take(n)`, `timeout`, `switchMap` replacing an inner source, application code calling `dispose()`, or binder/lifecycle shutdown.

~~~java
Flux<Long> shortStream = Flux.interval(Duration.ofSeconds(1))
        .take(3)
        .doFinally(signal -> log.info("finished: {}", signal));
~~~

`take(3)` intentionally caps the stream. If left accidentally inside an infinite event pipeline, the subscriber stops after three events. Never leave `take(1)` in production code after "quick testing."

### 6.4. Distinguishing with Logging

~~~java
Function<Flux<String>, Flux<String>> observed() {
    return input -> input
            .doOnSubscribe(s -> log.info("SUBSCRIBED"))
            .doOnRequest(n -> log.info("REQUEST {}", n))
            .doOnNext(v -> log.debug("NEXT"))
            .doOnError(e -> log.error("ERROR", e))
            .doOnCancel(() -> log.warn("CANCELLED"))
            .doFinally(signal -> log.warn("FINAL SIGNAL {}", signal));
}
~~~

Place instrumentation at stream entry, after key operators, and near the output binding when hunting where signals vanish. Never put sensitive payloads or dynamic event IDs into metric tags; use controlled logs/traces.

## 7. Subscribed, Yet Zero Demand

Reactive Streams require downstream `request(n)` calls to receive data. If subscribed without requesting, a backpressure-respecting Publisher emits no `onNext`.

Illustrative zero-request example:

~~~java
Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        log.info("subscribed but no request");
        // No request(1): a demand-respecting source emits nothing.
    }

    @Override
    protected void hookOnNext(Integer value) {
        log.info("next {}", value);
        request(1);
    }
});
~~~

This is a standalone Reactor mechanics example, not a production binder. When debugging, if `doOnSubscribe` logs while `doOnNext` does not, inspect `doOnRequest`, slow or blocking downstream operators, the data source, schedulers, and the binder. Do not immediately assume a missing subscriber.

In regular Kafka/Rabbit binders, using `Flux` types **does not mean** the broker enforces end-to-end Reactive Streams backpressure. Lowering downstream demand does not necessarily throttle broker delivery directly.

## 8. `block()` and Synchronous I/O Can Stall the Pipeline

Another cause of stalled pipelines is **the subscriber still exists, but threads or schedulers are wedged**.

Problematic pattern:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> badBlocking() {
    return source -> source.map(order -> {
        // Synchronous DB repository or blocking HTTP call.
        String result = blockingRemoteClient.call(order.orderId());
        return new OrderAccepted(order.orderId(), result);
    });
}
~~~

Running on an event-loop or non-blocking scheduler, synchronous I/O starves other signals; in some cases calling `block()` on a non-blocking thread throws a Reactor exception.

If you cannot replace the dependency with a non-blocking API yet, isolate the blocking call:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> boundedBlocking() {
    return source -> source.concatMap(order ->
            Mono.fromCallable(() ->
                    new OrderAccepted(
                            order.orderId(),
                            blockingRemoteClient.call(order.orderId())))
                .subscribeOn(Schedulers.boundedElastic()));
}
~~~

`boundedElastic` offloads blocking work to a bounded worker pool; it does not turn a blocking API into non-blocking I/O. Cap concurrency, timeouts, connection pools, and pending queues. If the domain permits parallel execution, you can use `flatMap(..., concurrency)` while accounting for ordering and acknowledgment impacts.

## 9. Do Not Confuse Reactive APIs with Reactive Binders

Spring Cloud Stream allows defining `Function<Flux<T>, Flux<R>>` even with the regular Kafka binder or RabbitMQ binder. However, a reactive Publisher inside your business function **does not automatically provide end-to-end Reactive Streams backpressure from broker to producer**.

| Binder | Underlying Consumer/Producer | What to Note |
|---|---|---|
| Regular Kafka binder | Spring for Apache Kafka message-listener container | Reactive API inside the function; do not assume end-to-end backpressure |
| Kafka Reactive Binder | Reactor Kafka `KafkaReceiver` and `KafkaSender` | End-to-end reactive; distinct ack/offset semantics |
| RabbitMQ binder | Spring AMQP / Spring Integration | Queue delivery, prefetch, and consumer acks; not Reactor Kafka |
| Pulsar binder | Depends on binder/client generation and reactive support | Check subscriber/ack semantics in your actual implementation |

Kafka Reactive Binder artifact:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-reactive</artifactId>
</dependency>
~~~

Use this artifact only at a BOM-supported version and when you genuinely need the reactive Kafka model. Never add both Kafka binders at once to "fix" a silent stream without checking type selection and bindings. Switching binders requires integration tests because offset, retry, conversion, and backpressure semantics change.

## 10. Kafka Reactive Binder: A Subscriber Does Not Replace Ack

In the Kafka Reactive Binder, offsets do **not auto-commit by default** in the same way as the regular Kafka binder. Per docs for 4.0.2+, received messages can carry `KafkaHeaders.ACKNOWLEDGMENT` holding a `ReceiverOffset` for the app to acknowledge after processing. `reactiveAtmostOnce` and `reactiveAutoCommit` are two alternatives with different semantics where that acknowledgment header is absent.

| Mode | Where Offset Commits | Risk |
|---|---|---|
| Manual ack/commit | App calls acknowledge/commit after processing | Forgetting ack stalls lag; early ack risks losing side effects |
| `reactiveAtmostOnce=true` | Binder commits before processing polled records | Can lose business updates on crash |
| `reactiveAutoCommit=true` | Binder auto-commits per processed batch | Requires understanding nested Flux batches and failure semantics |

In manual mode, **ensure side effects finish before acking**. Illustrative Reactor flow:

~~~java
@Bean
Function<Flux<Message<OrderCreated>>, Mono<Void>> consumeOrders(
        OrderService service) {

    return inbound -> inbound.concatMap(message ->
            service.saveReactively(message.getPayload())
                .doOnSuccess(ignored -> {
                    ReceiverOffset offset = message.getHeaders()
                            .get(KafkaHeaders.ACKNOWLEDGMENT,
                                 ReceiverOffset.class);
                    if (offset != null) {
                        offset.acknowledge();
                    }
                }))
        .doOnError(e -> log.error("reactive Kafka sink failed", e))
        .then();
}
~~~

Required imports include `reactor.core.publisher.Flux`, `reactor.core.publisher.Mono`, `org.springframework.messaging.Message`, `org.springframework.kafka.support.KafkaHeaders`, and `reactor.kafka.receiver.ReceiverOffset`. This assumes the matching Kafka Reactive Binder/version, manual mode, and `saveReactively` completing only after durable persistence. It does not apply directly to the regular Kafka binder, where the acknowledgment header can hold Spring Kafka's `Acknowledgment`. Check your version's API and never ack inside `doOnNext` before an async `Mono` completes.

**Dangerous bug:** "fixing" a subscriberless pipeline by adding `subscribe()` while forgetting acknowledgment lets the app log "processed" while committed offsets never advance. On restart, records are redelivered. Conversely, acking too early drops side effects on crashes.

### 10.1. `reactiveAutoCommit` Mode Produces Nested Fluxes

Kafka Reactive Binder docs note that `reactiveAutoCommit` can yield `Flux<Flux<ConsumerRecord<...>>>`, where each inner Flux represents records from one poll/batch. The application must process inner Fluxes and native deserializers properly—never subscribe to the outer Flux and abandon inner Fluxes.

Do not switch to `reactiveAutoCommit` just to make lag metrics drop. Verify payload conversion, acknowledgments, batch completion, and failure tests. Behavior also varied in older patch versions, so check documentation matching your deployed release.

## 11. `onError` Is Terminal: Where Should Recovery Live?

In Reactor, an unhandled error travels to the Subscriber as `onError` and terminates the subscription. A broker-wired pipeline might process 100 events cleanly, hit an error on event 101, and never receive another event. That is why monitoring must track **terminal signals**, not just per-message exception counts.

### 11.1. Wrong: Catching Errors at the End and Terminating the Whole Stream

~~~java
Function<Flux<OrderEvent>, Flux<OrderResult>> badRecovery() {
    return incoming -> incoming
            .map(this::transform)
            .onErrorResume(error -> {
                log.error("failed", error);
                return Flux.empty();
            });
}
~~~

Here `onErrorResume` handles **errors on the entire upstream Flux**. When one event throws inside `transform`, the pipeline switches to `Flux.empty()` and terminates. It **never resumes** subsequent events. If the handler must keep running after an individual business failure, scope recovery **per event**.

### 11.2. Better Targeted: Handle Errors Inside Each Inner Mono

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> resilientSink(
        OrderService service,
        QuarantineService quarantine) {

    return source -> source.concatMap(event ->
            Mono.defer(() -> service.process(event))
                .timeout(Duration.ofSeconds(10))
                .retryWhen(Retry.backoff(3, Duration.ofMillis(250))
                        .filter(error -> error instanceof TimeoutException))
                .onErrorResume(error -> {
                    log.error("event failed after retries", error);
                    return quarantine.storeDurably(event, error);
                }))
        .doOnError(error -> log.error(
                "terminal upstream or recovery error", error))
        .doFinally(signal -> log.warn(
                "resilientSink stopped: {}", signal))
        .then();
}
~~~

Assume `OrderService.process` and `QuarantineService.storeDurably` both return `Mono<Void>`. `Mono.defer` recreates the service call on each retry; `retryWhen` retries only that single event; `onErrorResume` durably quarantines the failed event. Once quarantined, the outer stream continues to the next event.

This pattern manages errors inside the pipeline, **not end-to-end delivery guarantees by itself**. In manual ack mode, ack only after business work or durable quarantine succeeds. If quarantining also fails, let errors propagate to your designed redelivery/stop/pause mechanism rather than dropping messages as successful.

**Note on retries:** timeouts or cancellations can occur after a side effect happened but before the app received the response. Retries can repeat side effects; protect critical actions with event IDs/idempotency keys and database transactions or idempotent APIs.

### 11.3. Avoid `onErrorComplete` and `onErrorContinue` Without Knowing the Consequences

- `onErrorComplete()` turns errors into completion, silently killing an infinite subscription.
- `onErrorReturn(...)` emits a fallback value and terminates the upstream after an error.
- `onErrorContinue(...)` has operator-dependent semantics that complicate state reasoning; Reactor recommends handling errors inside inner Publishers to isolate individual items.
- Pipeline-wide `retry()` resubscribes to the source, which on hot sources or broker consumers can cause replays, duplicates, or continuous error loops.

Never use these operators merely to silence error logs. Every error branch needs an explicit policy: bounded retry, quarantine/DLQ, redelivery, alerting, or intentional stop.

### 11.4. Imperative Binder Retries Do Not Automatically Apply to Reactive Functions

Spring Cloud Stream applies framework-level retry/error handling to imperative functions invoked per message. A reactive function is typically invoked once to assemble the Publisher; afterward the framework cannot wrap each individual item invocation the same way. Therefore, never assume `maxAttempts`, `retryableExceptions`, or binder DLQ settings handle exceptions **inside** a Reactor chain identically to imperative handlers.

For reactive functions, pair Reactor operators with broker-appropriate ack/retry mechanics. A broker-configured DLQ may still catch certain transport/deserialization failures, but async errors inside `flatMap` will not automatically go there. Verify every error path with integration tests.

## 12. Operators That Silently Stall or Complete Pipelines

Some operators stop output without throwing exceptions:

| Operator | Common Trap | How to Spot |
|---|---|---|
| `filter` | Predicate always returns false | Count items before vs after filter |
| `take(n)` | Completes after n messages | Look for `doFinally` = onComplete/cancel |
| `next()` | Takes only the first item from Flux | Check signature returning Mono |
| `takeUntil`/`takeWhile` | Condition triggers early termination | Log condition; test boundaries |
| `timeout` | No item within window → onError | Check timeout logs and retry policy |
| `onErrorResume(Flux.empty())` | Errors converted to completion | Look for global error fallback |
| `ignoreElements`/`then()` | Intentionally drops `onNext` outputs | Use only for output-less sinks |
| `zip` with an empty Mono | Produces no output tuples | Count emissions per branch |
| `switchMap` | Cancels prior inner task when new event arrives | Use `flatMap`/`concatMap` unless cancellation is intended |
| `collectList` on infinite Flux | Waits forever for completion before emitting | Never collect unbounded streams |
| `buffer`/`window` | Waits for count/time before emitting | Check size, timeout, and demand |
| `publish().autoConnect(n)` | Never connects until n subscribers join | Track subscriber count |
| `publish().refCount(n)` | Disconnects when subscribers drop | Verify lifecycle and refCount |

### 12.1. Never Wait for an Infinite Flux to Complete

~~~java
// Anti-pattern: a broker stream never completes normally.
Mono<List<OrderEvent>> allEvents = incoming.collectList();
~~~

When `incoming` is a live event stream, `collectList` emits nothing until upstream completes while buffering unbounded items in RAM. For aggregation, use `bufferTimeout`, `windowTimeout`, keyed windows, or bounded state stores designed for the task.

### 12.2. `switchMap` Can Cancel In-Flight Work

~~~java
Flux<OrderResult> results = incoming
        .switchMap(service::processAndReturn);
~~~

When a new event arrives before the previous inner Publisher finishes, `switchMap` cancels the previous subscription. For order processing, that is rarely what you want. Use `concatMap` to preserve order one item at a time, or `flatMap(..., concurrency)` when parallel execution and out-of-order completion are acceptable.

### 12.3. Unbounded `flatMap` Can Overwhelm Downstream Services

`flatMap` runs many inner Publishers concurrently, which with a slow backend piles up pending requests, connections, and buffers. Cap concurrency explicitly:

~~~java
Flux<OrderResult> results = incoming.flatMap(
        event -> service.processAndReturn(event)
                .timeout(Duration.ofSeconds(8)),
        16);
~~~

`16` is illustrative only. Measure DB pools, HTTP client limits, ordering, and ack semantics before tuning; raising concurrency never replaces binder backpressure.

## 13. Reactive Suppliers Invoked Once and Completed Sources

Spring Cloud Function distinguishes imperative `Supplier<T>` (typically polled) from reactive `Supplier<Flux<T>>` (typically returning a long-lived continuous stream, invoked once).

### 13.1. Using a Finite Supplier While Expecting New Messages

~~~java
@Bean
Supplier<Flux<String>> threeMessagesOnly() {
    return () -> Flux.just("one", "two", "three");
}
~~~

If the app emits three messages and stops, that is expected finite `Flux` behavior, not a dead subscriber. If an infinite source is needed, design a proper long-lived Publisher—such as a Reactor/connector source emitting on events with proper lifecycle/cancel handling.

### 13.2. Never Use `share()` to Fake an Infinite Stream

`share()` turns a cold source into a hot multicast for subscribers, but it **never turns** a finite `Flux.just` into an infinite stream. Once exhausted, the stream still completes. `repeat()` can replay items, though on business events it easily generates unwanted duplicates.

### 13.3. Polling Finite Sources Intentionally

For periodic batch reads, `@PollableBean` signals to the framework that a finite reactive Supplier should be polled via compatible mechanics. Check `spring.integration.poller.*` and per-binding poller settings, and never use polling to patch around an erroring or canceled output publisher.

## 14. Hot Sinks: Emitting Before Subscribers Exist

For external sources (HTTP/WebSocket, SDK callbacks, custom connectors), developers often bridge with `Sinks.Many`:

~~~java
class EventGateway {
    private final Sinks.Many<String> sink =
            Sinks.many().multicast().directBestEffort();

    Sinks.EmitResult publish(String value) {
        return sink.tryEmitNext(value);
    }

    Flux<String> flux() {
        return sink.asFlux();
    }
}
~~~

With `multicast().directBestEffort()`, emitting when no subscriber is present returns `FAIL_ZERO_SUBSCRIBER`. If code ignores `EmitResult`, callers assume the message was dispatched even though no consumer existed. When using Sinks:

1. Check `EmitResult` rather than treating every emit call as succeeded.
2. Subscribe before accepting events, or choose an appropriate replay/buffer strategy.
3. For critical events, use durable queues/logs (Kafka/RabbitMQ/Pulsar) instead of RAM-only buffers.
4. Bound buffers and define overflow/backpressure policies.
5. Close or emit error/complete cleanly on shutdown.

In-memory sinks do not replay across process crashes. Switching from direct-best-effort to replay/buffer reduces pre-subscriber drops at the cost of higher RAM and changed semantics, so define explicit retention limits.

## 15. Verify the Function Is Actually Bound

When Reactor code is sound yet zero events flow, re-check Spring Cloud Stream wiring. Having a bean in the Spring context **is not enough**; it must be selected and bound to the right middleware.

### 15.1. Check Definition and Binding Names

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
    stream:
      bindings:
        normalize-in-0:
          destination: raw.orders
          group: normalize-service
        normalize-out-0:
          destination: clean.orders
~~~

Java:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> normalize() {
    return source -> source.map(this::normalizeEvent);
}
~~~

For function `normalize`, the exact names are `normalize-in-0` and `normalize-out-0`. Common pitfalls:

- `definition` points to a different bean.
- Bean named `normalize` is not the functional bean actually selected.
- Multiple `Supplier`/`Function`/`Consumer` beans exist without an explicit `definition`.
- `spring.cloud.stream.function.autodetect=false` disables auto-discovery in another config layer.
- Switched to function composition without updating binding names/aliases.
- Wrong input destination, consumer group, binder name, serializer/deserializer, or content type.
- Output binding misconfigured or target middleware rejects publishes.

Never blame a missing subscriber if `BindingService` never bound the input in the first place.

### 15.2. Check Actuator Bindings When Supported

If the application includes Spring Boot Actuator and Spring Cloud Stream's bindings endpoint is enabled in your version, check binding state at `/actuator/bindings`. Expose and secure the endpoint explicitly; never leave actuator public.

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,bindings
~~~

Check whether the binding is `STARTED`, `STOPPED`, or another state per binder/version. This endpoint diagnoses binding lifecycle; it **does not prove** every Reactor subscription inside the function is alive or that business messages are being processed.

### 15.3. Inspect the Underlying Broker Source

| Broker | What to Check |
|---|---|
| Kafka | Topic, group ID, partition assignment, committed offset, lag, deserialization errors |
| RabbitMQ | Queue name/vhost, exchange bindings, ready/unacked, consumer count, ack/prefetch |
| Pulsar | Topic/subscription name/type, backlog, cursor, ack/redelivery, authentication |

A Kafka group with 6 consumers on a 3-partition topic leaves some consumers unassigned; those instances see zero events despite a valid reactive subscription. RabbitMQ shares queue deliveries across consumers, so one instance may get fewer events. Pulsar subscription types (`Shared`/`Failover`/`Key_Shared`) similarly govern distribution. Check broker state before adding `subscribe()` to code.

## 16. Placing Reactor Logging in the Right Spots

Add probes at multiple stages to see where events vanish:

~~~java
@Bean
Function<Flux<String>, Flux<String>> tracePipeline() {
    return input -> input
            .doOnSubscribe(s -> log.info("01 input subscribed"))
            .doOnRequest(n -> log.debug("02 requested {}", n))
            .doOnNext(v -> log.debug("03 input event received"))
            .map(this::normalize)
            .doOnNext(v -> log.debug("04 after normalize"))
            .filter(this::isAllowed)
            .doOnNext(v -> log.debug("05 after filter"))
            .doOnError(e -> log.error("06 error", e))
            .doFinally(signal -> log.warn("07 terminal {}", signal))
            .checkpoint("normalize-orders");
}
~~~

Interpretation:

- No `01`: no subscription on the instrumented Publisher, or the function is unbound.
- `01` without `02`: investigate downstream demand; also check the source.
- `02` without `03`: does the broker have data, and how are partitions/queues assigned?
- `03` without `04`: did `transform` throw, block, or cancel?
- `04` without `05`: did the `filter` predicate drop every event?
- `06` or `07`: inspect the terminal cause and why the subscriber stopped.

`checkpoint("normalize-orders")` tags assembly sites to trace error paths at far lower cost than global `Hooks.onOperatorDebug()`. Enable the global debug hook only briefly during diagnosis or in test environments, since capturing stack traces for every operator is expensive.

### 16.1. Never Log Every Payload in Production

Logging `onNext` for every event under high throughput burns I/O and risks leaking data. Use sampling, aggregate counters, controlled event/correlation IDs, error traces, and metrics. Never put event IDs or user IDs into Prometheus labels due to unbounded cardinality.

## 17. Metrics Confirming Whether Subscriptions Stay Alive

Track together:

| Metric / Signal | Meaning |
|---|---|
| `stream.reactive.subscriptions.started` | Total `onSubscribe` events |
| `stream.reactive.subscriptions.active` | Currently active subscriptions (gauge) |
| `stream.reactive.termination` | Completions/errors/cancellations with bounded tags |
| `stream.messages.received` | Total events entering the pipeline |
| `stream.messages.processed` | Successfully processed events |
| `stream.messages.failed` | Failed events |
| `stream.processing.duration` | Processing duration timer/histogram |
| `stream.last.onnext.age` | Time elapsed since last `onNext` |
| Kafka consumer lag | Unprocessed records in group/partition |
| RabbitMQ ready/unacked | Queued vs delivered-unacked messages |
| Pulsar subscription backlog | Messages pending on subscription |

These `stream.*` names are **application-defined metric examples**, not guaranteed built-in Spring Cloud Stream metrics. Track subscription state via `doOnSubscribe`/`doFinally` or lifecycle hooks rather than inferring it from Actuator health.

Gauge increment/decrement example:

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Gauge.builder("stream.reactive.subscriptions.active", subscriptions,
        AtomicInteger::get)
    .tag("binding", "normalize-in-0")
    .register(meterRegistry);

Flux<String> observed = incoming
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .doFinally(signal -> subscriptions.decrementAndGet());
~~~

This is illustrative instrumentation. Register gauges once at component initialization rather than per message, and pair each `doOnSubscribe` with one `doFinally` on the same subscription. Across multiple replicas, aggregate by binding/instance while bounding cardinality.

### 17.1. Reading Combined Signals

| Active Subscriptions | Broker Backlog | Successful Processing | Interpretation |
|---|---|---|---|
| 0 | Growing | 0 | Lost subscriber or binding never started |
| 1 | Growing | 0 | Subscribed, but blocked, demand=0, or processing failing |
| 1 | 0 | 0 | Source genuinely has no messages |
| 1 | Growing | Growing slowly | Under-provisioned, slow downstream, or retries |
| 1 | Shrinking | Growing | Pipeline is draining backlog |

On Kafka, if an instance holds zero assigned partitions, `active=1` with zero `onNext` is normal. Never alert solely on `lastOnNextAge` without factoring in arrival rates and partition assignments.

## 18. Testing with `StepVerifier`

Project Reactor provides `reactor-test` and `StepVerifier` to assert that a Publisher actually emits, completes, or errors. Example unit test for a transform Function:

~~~java
@Test
void normalizeProcessesEveryItemOnSubscription() {
    Function<Flux<String>, Flux<String>> fn =
            input -> input.map(String::toUpperCase);

    StepVerifier.create(fn.apply(Flux.just("a", "b")))
            .expectNext("A", "B")
            .verifyComplete();
}
~~~

`StepVerifier.create` acts as the Subscriber created by the test, causing the function's operators to execute.

### 18.1. Test That Without a Subscriber Nothing Executes

~~~java
@Test
void coldSourceNeedsSubscriber() {
    AtomicInteger executions = new AtomicInteger();

    Flux<Integer> source = Flux.defer(() -> {
        executions.incrementAndGet();
        return Flux.just(1, 2);
    });

    assertEquals(0, executions.get());

    StepVerifier.create(source)
            .expectNext(1, 2)
            .verifyComplete();

    assertEquals(1, executions.get());
}
~~~

This proves that for a cold source, assembly alone runs no work. Hot publishers have different semantics and need dedicated tests.

### 18.2. Test Per-Item Error Isolation

~~~java
@Test
void perEventRecoveryKeepsFollowingEvents() {
    Flux<Integer> source = Flux.just(1, 2, 3);
    Flux<Integer> result = source.concatMap(value ->
            Mono.fromCallable(() -> {
                if (value == 2) {
                    throw new IllegalArgumentException("bad event");
                }
                return value * 10;
            }).onErrorResume(error -> Mono.empty()));

    StepVerifier.create(result)
            .expectNext(10, 30)
            .verifyComplete();
}
~~~

This tests Reactor semantics only; in production, never silently discard failing events if business rules require quarantine/DLQ or redelivery. Real recovery tests must verify durable storage of failed messages.

### 18.3. Test Terminal Signals

~~~java
@Test
void unhandledErrorTerminatesFlux() {
    Flux<String> source = Flux.just("ok", "bad", "later")
            .map(value -> {
                if (value.equals("bad")) {
                    throw new IllegalStateException("broken");
                }
                return value;
            });

    StepVerifier.create(source)
            .expectNext("ok")
            .expectError(IllegalStateException.class)
            .verify();
}
~~~

Add tests for cancellation (`thenCancel`), timeouts (using virtual time where suitable), unsubscribed hot sinks, and lifecycle disposal where applicable.

### 18.4. Test the Binder, Not Only the `Flux`

`StepVerifier` unit tests cannot catch:

- Wrong `spring.cloud.function.definition`.
- Missing output bindings.
- Unassigned partitions in a Kafka group.
- Misnamed RabbitMQ queues or Pulsar subscriptions.
- Kafka Reactive Binder failing to commit offsets after processing.
- Producer send failures occurring after a `doOnNext` log ran.

Pair `StepVerifier` with Spring Cloud Stream Test Binder for function/binding wiring and **integration tests against real brokers** (e.g., Testcontainers Kafka/RabbitMQ) covering startup, subscriptions, acks, retries, DLQs, and process restarts. Test Binder does not fully emulate broker-specific semantics.

## 19. Real-World Case: Reactive Kafka Sink Dies After the First Error

An application using the Kafka Reactive Binder reads `orders.created` with this function:

~~~java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> sink(OrderService service) {
    return flux -> flux
            .flatMap(service::saveReactively)
            .then();
}
~~~

Initially the consumer runs smoothly. When one event hits a DB error, the inner `Mono` emits `onError`; `flatMap` propagates it outward; `then()` terminates with error; the subscription dies. The Spring Boot process still reports HTTP healthy. New events pile up in Kafka and lag grows.

Diagnosis:

1. Verify `sink-in-0` is bound to the right Kafka group.
2. Confirm `doOnSubscribe` ran.
3. Add `doOnError`, `doFinally`, and `checkpoint`.
4. Observe terminal `ON_ERROR` immediately following the DB exception.
5. Inspect ack/offset mode: was the failing message acked or does it need redelivery?
6. Move retry/quarantine **inside the inner Mono for each event**.
7. Test restarts and duplicate delivery before deploying.

The fix can follow `resilientSink` from section 11 plus explicit acknowledgment/quarantine. Never just append `onErrorResume(error -> Mono.empty())` at the outer stream end: that completes the whole subscription and stops processing future events.

## 20. Runbook When a Pipeline Stops Processing Messages

### Step 1 — Verify Real Messages Exist at the Source

Inspect topic/queue/subscription and message counts on the broker:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-persistence
~~~

For RabbitMQ, check `messages_ready`, `messages_unacknowledged`, and consumer count. For Pulsar, check subscription backlog and consumer status. Do not overlook read permissions, TLS, and deserializers.

### Step 2 — Verify Function and Bindings

Check bean name, `spring.cloud.function.definition`, input/output binding names, binder type, consumer group, and destination. Inspect startup logs and `/actuator/bindings` if supported and enabled. A created bean that is not bound does not establish a reactive subscription.

### Step 3 — Verify Subscription and Demand

Add `doOnSubscribe`, `doOnRequest`, and `doOnNext` at the start of the Reactor pipeline. If a `Consumer<Flux>` merely assembles a Publisher, switch to `Function<Flux, Mono<Void>>` or manage a lifecycle-bound subscription. If it is a reactive Function, remove stray `subscribe()` calls and return the right Publisher to the framework.

### Step 4 — Locate Terminal Signals

Add `doOnError`, `doOnCancel`, and `doFinally`. Search for `take`, `next`, `onErrorComplete`, `onErrorResume(Flux.empty())`, `timeout`, and operators waiting for upstream completion. Trace errors with `checkpoint`.

### Step 5 — Check Schedulers and Downstream Dependencies

Inspect thread dumps, connection pools, HTTP/DB latencies, blocking calls, and queue capacities. Offload blocking calls to an appropriately bounded scheduler or migrate to non-blocking clients. Never raise concurrency/timeouts blindly to hide a deadlock.

### Step 6 — Check Offsets, Acks, and Retries

For the Kafka Reactive Binder, verify manual ack or auto-commit semantics. For regular Kafka/Rabbit/Pulsar binders, use that binder's native ack/transaction mechanics rather than copying Reactor Kafka code. Inspect poison messages, exhausted retries, DLQs, and subscription health after errors.

### Step 7 — Controlled Recovery

Once a subscription terminates, waiting longer will not revive it. Fix the root cause and re-establish the stream through a valid lifecycle (such as a controlled service restart) **only after securing offsets/acks and idempotency**. Never create an infinite resubscribe loop on the same failing record; that triggers retry storms, duplicates, and broker overload.

### Step 8 — Confirm Sustained Healthy Processing

Verify events continue passing checkpoints, processed rates rise, Kafka lag/Rabbit queue depth/Pulsar backlog shrink, terminal errors stop recurring, DLQ matches policy, and side effects do not duplicate. Monitor long enough across multiple batches and peak traffic; one successful event does not prove recovery is complete.

## 21. Quick Remediation Decision Table

| Evidence | Priority Diagnosis | Change to Try |
|---|---|---|
| `Consumer<Flux>` builds pipeline then returns | Unsubscribed | Switch to `Function<Flux,Mono<Void>>` or manage subscription |
| `Function<Flux,Flux>` calls `subscribe()` and returns another Flux | Detached subscription | Return a single unified operator chain to the framework |
| `doOnSubscribe` never logs | Wiring or Publisher unsubscribed | Check `definition`/bindings; hold off touching the broker |
| Subscribed, yet request is 0 | Demand/backpressure | Inspect Subscriber/operators and source |
| `doFinally` = `ON_ERROR` | Terminal error | Per-event recovery, log/trace, ack policy |
| `doFinally` = `ON_COMPLETE` | Finite source or completing operator | Check Supplier, `take`, `collectList` |
| `doFinally` = `CANCEL` | Cancel/dispose/`switchMap`/shutdown | Trace subscription owner |
| `onNext` before `filter`, none after | Filter drops everything | Inspect predicate and schema |
| Kafka lag grows, zero assignments | Consumer group/partitions or connection | Check group state and partition count |
| Output empty while function input has data | Output binding/operator send | Check destination, serialization, producer errors |
| Hot `Publisher` emits before subscriber | Early emission | Handle `EmitResult`, lifecycle, durable queue |
| Subscribed, yet high CPU / stalled | Blocking / scheduler starvation | Thread dump, `boundedElastic`, or non-blocking I/O |
| Lag stays flat after subscribing | Missing ack, downstream error, or stalled source | Check offsets, acks, retries, and DB |

## 22. Common Mistakes

1. **Thinking creating a Flux executes it:** operators run only with a proper subscription.
2. **Assuming every reactive Consumer is auto-subscribed:** `Consumer<Flux<?>>` returns `void`, leaving subscription to the application.
3. **Calling `subscribe()` inside a reactive Function:** spawns two independent streams, duplicate side effects, and lost errors.
4. **Ignoring terminal signals:** a single `onError` or `onComplete` can silence a pipeline permanently.
5. **Putting `onErrorResume(Flux.empty())` at the stream tail:** kills the entire stream on error instead of recovering per event.
6. **Using `onErrorContinue` to swallow exceptions:** complex semantics that can silently drop data.
7. **Calling `collectList()` on an infinite broker stream:** waits forever to complete and exhausts memory.
8. **Leaving `take(1)` or `next()` in production flows:** consumes only a handful of events then stops.
9. **Using `switchMap` for mandatory side effects:** cancels in-flight work whenever a new event arrives.
10. **Running blocking I/O on event-loop threads:** causes starvation or exceptions on `block()`.
11. **Assuming the regular Kafka binder is end-to-end reactive because the function uses Flux:** does not automatically provide full Reactive Streams backpressure.
12. **Switching to Reactive Kafka Binder without handling acknowledgments:** consumer runs while offsets never advance or commit at the wrong time.
13. **Expecting imperative binder `maxAttempts` to fix async Reactor errors:** requires reactive error policies and integration tests.
14. **Skipping function definition/binding checks:** bean existence does not mean broker data arrives.
15. **Adding another `subscribe()` when `onNext` is silent:** if Kafka partitions are unassigned, this fixes nothing.
16. **Treating Actuator health UP as proof of an active subscriber:** monitor subscription lifecycles and business throughput.
17. **Testing Fluxes only with `StepVerifier`:** misses wrong binders, offsets, DLQs, and broker disconnects.
18. **Restarting in a loop to recover:** triggers rebalances, replays, and retry storms if the root error remains unfixed.

## Conclusion

When a Spring Cloud Stream reactive pipeline stops processing, first distinguish **no subscriber**, **subscribed with zero demand/data**, and **terminated subscription** due to complete/error/cancel. `Function<Flux,Flux>` should normally **return** a Publisher for the framework to subscribe to, whereas `Consumer<Flux>` must manage its own subscription; for reactive sinks, `Function<Flux,Mono<Void>>` is the documented recommendation. A finite reactive Supplier completing can be intentional design rather than a bug.

For durable recovery, do not simply add `subscribe()` or restart Pods. Check `spring.cloud.function.definition` and bindings, place Reactor instrumentation at the start/middle/end of the pipeline, identify terminal signals, isolate error handling per event, configure ack/offset behavior for your exact binder, and test duplicates/replays. Reactor APIs do not magically alter Kafka/RabbitMQ/Pulsar semantics. Declare the pipeline recovered only when both subscriptions and broker backlog/processing metrics stabilize.

## References

- [Spring Cloud Stream — Producing and Consuming Messages: Consumer (Reactive) and Reactive Functions Support](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming Model: Reactive Function and Consumer](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Kafka Reactive Binder Basic Examples](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/examples.html)
- [Spring Cloud Stream — Kafka Reactive Binder Consuming Records](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/consuming.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
