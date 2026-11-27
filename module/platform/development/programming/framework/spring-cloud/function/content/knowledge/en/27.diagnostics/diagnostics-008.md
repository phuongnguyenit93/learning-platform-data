# Flux Stream Not Processed Due to Missing Subscription

## 1. Symptom: Flux Is Created, Yet Nothing Happens

A Spring Cloud Function application defines an order-processing function:

~~~java
@Bean
public Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders
        .map(this::normalize)
        .flatMap(orderService::process);
}
~~~

The code starts up normally, the bean appears in the Spring context, yet logs inside `map` or `orderService.process` never run. Common manifestations:

- Calling `Flux.just(...)` or `Flux.fromIterable(...)`, yet no events are processed.
- Adding `map`, `filter`, or `doOnNext`, yet no side effects occur.
- A method returns `Flux<OrderReceipt>`, yet the caller merely stores the variable and sees no result.
- `collectList()` or `then()` was called, yet the database or API is never invoked.
- A `Supplier<Flux<T>>` is declared, yet no messages are published to the broker.
- A `Consumer<Flux<T>>` receives a publisher, yet the consumer never executes.
- A unit test constructs a pipeline cleanly, yet no assertion triggers subscription.
- The application runs behind HTTP or Spring Cloud Stream, yet the stream carries no messages even though the function bean was created.

The most common cause is **no Subscriber registered with the Publisher**. In Project Reactor, a `Flux` describes an asynchronous processing chain; it is not an already-executed collection. Operators like `map`, `filter`, and `flatMap` merely assemble the pipeline. Data begins flowing only when a subscription and downstream demand exist.

This lesson belongs to the **Diagnostics** chapter, titled **"Flux Stream Not Processed Due to Missing Subscription"**, within the **SPRING_CLOUD_FUNCTION** module. The module teaches developing reusable business logic using `Supplier`, `Function`, and `Consumer`, looking up via `FunctionCatalog`, converting messages, and deploying the same function via HTTP, events, or serverless.

**First diagnostic question:** who is subscribing to this publisher?

### Learning Objectives

After this lesson, you will be able to:

1. Explain the Publisher–Subscriber lifecycle and why a pipeline does not run without a subscription.
2. Distinguish assembly, subscription, request, `onNext`, `onError`, `onComplete`, and cancellation.
3. Spot pipelines dropped because a publisher was not returned or not subscribed to at the call boundary.
4. Choose the right reactive signatures for `Function` and `Consumer`.
5. Understand how Spring Cloud Stream wires and subscribes to reactive functions.
6. Distinguish continuous reactive `Supplier`s from finite reactive `Supplier`s requiring polling.
7. Diagnose cold/hot publishers, multiple subscriptions, backpressure, errors, and cancellations.
8. Test with `StepVerifier` to ensure the pipeline actually executes.
9. Manage manual subscriptions across lifecycles cleanly when manual subscription is genuinely required.

## 2. Flux Is a Stream Blueprint, Not an Executed List

A `Flux<T>` represents a sequence that can emit from 0 to N elements, ending in completion or error. Declaring:

~~~java
Flux<String> names = Flux.just("anna", "minh", "linh");
~~~

only creates a publisher. No subscriber has requested data yet.

Likewise:

~~~java
Flux<String> upperNames = names.map(String::toUpperCase);
~~~

`map` creates a new publisher describing the transformation. It does not execute the transformation when that line runs.

### 2.1. Assembly and Subscription

~~~mermaid
flowchart TD
    A["Create source: Flux.just(...)"] --> B["Assembly: map / filter / flatMap"]
    B --> C["Assembled publisher pipeline"]
    C --> D{"Is there a Subscriber?"}
    D -->|No| E["No data signals emitted"]
    D -->|Yes| F["Subscriber subscribes and requests"]
    F --> G["Source emits onNext"]
    G --> H["Operators process"]
    H --> I{"More data?"}
    I -->|Yes| G
    I -->|No| J["onComplete or onError"]
~~~

Three phases to distinguish:

| Phase | What happens | Is data processed yet? |
| --- | --- | --- |
| Assembly | Create source and attach operators | Usually not yet |
| Subscription | Subscriber registers; subscription is established | Pipeline is activated |
| Demand/processing | Subscriber requests items; source emits signals | Yes |

In Reactive Streams, a subscriber not only signals interest, it also controls demand via `request(n)`. This forms the basis of backpressure.

### 2.2. Example of an Unexecuted Pipeline

~~~java
Flux<Integer> numbers = Flux.range(1, 3);

numbers.map(number -> {
    System.out.println("Processing " + number);
    return number * 10;
});
~~~

No `Processing ...` line is printed because the resulting publisher was neither subscribed to nor returned to another component to subscribe.

### 2.3. Triggering in a Standalone Program

~~~java
Flux<Integer> numbers = Flux.range(1, 3);

numbers
    .map(number -> number * 10)
    .subscribe(System.out::println);
~~~

Output:

~~~text
10
20
30
~~~

`subscribe` establishes the subscription and activates the pipeline. However, do not turn calling `subscribe()` into a habit inside every Spring Cloud Function bean; in environments where an adapter manages the reactive lifecycle, return the publisher to the adapter.

## 3. Operators Do Not Subscribe on Their Own

Operators that often trick newcomers into thinking the pipeline ran:

| Operator | Purpose | Subscribes automatically? |
| --- | --- | --- |
| `map` | Transform each item | No |
| `filter` | Filter items | No |
| `flatMap` | Map each item into an inner publisher | No |
| `concatMap` | Concatenate inner publishers sequentially | No |
| `doOnNext` | Observe side effect when an item arrives | No |
| `doOnError` | Observe errors | No |
| `publishOn` | Switch scheduler for downstream | No |
| `subscribeOn` | Choose scheduler for upstream subscription | No |
| `collectList` | Collect items into `Mono<List<T>>` | No |
| `then` | Return publisher signaling only completion after upstream | No |
| `retryWhen` | Describe re-subscription upon error | No |

### 3.1. Side Effects in doOnNext Do Not Run Without Subscription

~~~java
AtomicInteger processed = new AtomicInteger();

Flux<Integer> pipeline = Flux.range(1, 3)
    .doOnNext(value -> processed.incrementAndGet());

System.out.println(processed.get()); // 0
~~~

`doOnNext` is a callback triggered when upstream emits an item. It is not a standalone execution command.

After subscribing:

~~~java
pipeline.subscribe();

System.out.println(processed.get()); // 3
~~~

### 3.2. collectList and then Also Only Build New Publishers

~~~java
Mono<List<Integer>> allNumbers =
    Flux.range(1, 3).collectList();

Mono<Void> completed =
    Flux.range(1, 3).then();
~~~

Both variables remain publishers. To run them in tests, use `StepVerifier` or subscribe. In reactive application code, return the publisher to the caller instead of blocking.

### 3.3. publishOn and subscribeOn Are Not Subscriptions

~~~java
Flux<Integer> pipeline = Flux.range(1, 10)
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::transform);
~~~

These two operators only choose execution contexts once subscription occurs. They neither create a subscriber nor trigger the source.

## 4. Three Core Signals and the Role of Request

A Reactive Streams publisher emits these signals:

- `onNext(value)`: a new element arrived.
- `onError(error)`: sequence terminated with an error.
- `onComplete()`: sequence completed normally.

The subscriber registers via `subscribe` and can request elements via `request(n)`.

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(value 1)
    P-->>S: onNext(value 2)
    S->>P: request(2)
    P-->>S: onNext(value 3)
    P-->>S: onComplete()
~~~

### 4.1. Subscription Without Demand

A custom subscriber can subscribe without calling `request`. In that case, the source has never been asked to emit items.

That is a "subscribed yet not processing" state, distinct from not subscribing at all.

### 4.2. Do Not Write Custom Subscribers Unnecessarily

In most applications, use Reactor's `subscribe` overloads or let Spring adapters manage subscriptions. Implementing `Subscriber` manually makes sense only when you need fine-grained demand control and understand the Reactive Streams contract thoroughly.

### 4.3. Backpressure Is Not Message Loss

Backpressure lets downstream request only as many items as it can handle. If a subscriber requests slowly, the source slows down to match demand; do not conclude data is lost simply because all events do not appear instantly.

## 5. How to Verify a Publisher Was Subscribed To

You can attach observation hooks:

~~~java
Flux<OrderEvent> source = orderSource.events()
    .doOnSubscribe(subscription ->
        log.info("Order stream subscribed")
    )
    .doOnRequest(count ->
        log.info("Order stream requested {}", count)
    )
    .doOnNext(event ->
        log.debug("Received order {}", event.orderId())
    )
    .doOnError(error ->
        log.error("Order stream failed", error)
    )
    .doOnCancel(() ->
        log.warn("Order stream cancelled")
    )
    .doOnComplete(() ->
        log.info("Order stream completed")
    );
~~~

Hooks execute only if subscription and corresponding signals occur.

| Hook | What it reveals |
| --- | --- |
| `doOnSubscribe` | A subscriber registered |
| `doOnRequest` | Downstream issued demand |
| `doOnNext` | Elements were emitted |
| `doOnError` | Pipeline ended with an error |
| `doOnComplete` | Pipeline completed normally |
| `doOnCancel` | Subscription was cancelled |

Do not log full payloads containing customer details, payment info, or secrets. Use approved event IDs, payload types, and correlation IDs.

## 6. Common Mistake: Assembling a Pipeline and Discarding the Result

Wrong example:

~~~java
public Flux<OrderReceipt> process(Flux<OrderEvent> orders) {
    orders.map(this::normalize)
        .flatMap(orderService::process);

    return Flux.empty();
}
~~~

The pipeline was assembled yet never returned. The method returns a separate empty publisher, so callers receive `Flux.empty()`.

Correct approach:

~~~java
public Flux<OrderReceipt> process(Flux<OrderEvent> orders) {
    return orders
        .map(this::normalize)
        .flatMap(orderService::process);
}
~~~

### 6.1. Dropping Inner Publishers Inside Callbacks

Wrong:

~~~java
orders.doOnNext(order ->
    orderService.save(order)
);
~~~

If `save` returns `Mono<Void>`, the inner publisher is discarded. `doOnNext` does not automatically subscribe to the inner `Mono`.

Right:

~~~java
return orders.concatMap(order ->
    orderService.save(order).thenReturn(order)
);
~~~

Or if only completion after saving is needed:

~~~java
return orders.concatMap(order ->
    orderService.save(order)
).then();
~~~

### 6.2. Do Not Nest subscribe to "Fix" Dropped Inner Publishers

Wrong:

~~~java
orders.subscribe(order ->
    orderService.save(order).subscribe()
);
~~~

This is nested fire-and-forget. The outer pipeline does not wait for the inner pipeline, errors and cancellation fail to propagate back to callers, and backpressure is broken across the boundary.

Chain publishers using `flatMap` or `concatMap`.

## 7. Function<Flux<T>, Flux<R>>: Return the Publisher to the Framework

Spring Cloud Function supports reactive functions:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders
        .map(this::normalize)
        .flatMap(orderService::process);
}
~~~

When Spring Cloud Stream uses this function, the reactive function is invoked once to connect the user processing pipeline to the binder's source/target streams. The binder/framework manages wiring and subscription.

Do not write:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> {
        orders
            .map(this::normalize)
            .flatMap(orderService::process)
            .subscribe();

        return Flux.empty();
    };
}
~~~

This flawed version subscribes to a detached pipeline and returns an empty publisher. The framework cannot manage outputs, errors, or cancellation of the detached pipeline.

### 7.1. Reactive Functions Are Invoked Once in Spring Cloud Stream

| Signature | Invocation in Spring Cloud Stream |
| --- | --- |
| `Function<OrderEvent,OrderReceipt>` | Once per event |
| `Function<Flux<OrderEvent>,Flux<OrderReceipt>>` | Once at startup to wire the stream |
| `Consumer<OrderEvent>` | Once per event |
| `Supplier<OrderEvent>` | Polled to obtain each value |
| `Supplier<Flux<OrderEvent>>` | Typically called once to produce a continuous stream |

A reactive function is a **stream initialization function**. Logic inside its operators runs as the binder source emits data and downstream subscriptions are established.

### 7.2. Having a Bean Does Not Mean a Subscriber Exists

Declaring `@Bean Function<Flux<T>,Flux<R>>` in `ApplicationContext` does not start any stream on its own. An execution context is needed:

- Spring Cloud Stream binds inputs/outputs and connects the stream.
- The HTTP adapter receives a request and subscribes to the response publisher.
- A direct caller invokes the function and subscribes to the returned publisher.
- A unit test uses `StepVerifier` to drive the publisher.

`FunctionCatalog` registers and resolves functions; merely having a name in the catalog is not a subscription.

## 8. Function<Flux<T>, Mono<Void>>: Preferred Reactive Consumer Pattern

When you only need to consume a stream without emitting an output payload, Spring Cloud Stream recommends `Function<Flux<T>,Mono<Void>>` over `Consumer<Flux<T>>`.

Service:

~~~java
public interface OrderService {
    Mono<Void> persist(OrderEvent event);
}
~~~

Function:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> persistOrders(
        OrderService orderService) {

    return orders -> orders
        .concatMap(orderService::persist)
        .then();
}
~~~

`concatMap` invokes persistence in order. `then()` creates a `Mono<Void>` that completes only when upstream finishes.

Because the framework receives the output publisher, it can manage subscription and pipeline lifecycle cleanly.

### 8.1. Why Is then() Not a Subscription?

~~~java
Mono<Void> completion = orders
    .concatMap(orderService::persist)
    .then();
~~~

`then()` converts a multi-value sequence into a completion-only publisher. It still has not subscribed. Persistence executes only when Spring Cloud Stream or a test subscribes to `completion`.

### 8.2. Do Not Use then() When Per-Event Output Is Needed

If you want to emit `OrderReceipt` to an output binding, return `Flux<OrderReceipt>`:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders(
        OrderService orderService) {

    return orders -> orders
        .concatMap(orderService::process);
}
~~~

Returning `Mono<Void>` emits no output payload; that is intentional for consumer-style functions.

## 9. Consumer<Flux<T>> Is a Special Case

Java `Consumer<T>` returns `void`. With `Consumer<Flux<OrderEvent>>`, the framework invokes the callback yet receives no resulting publisher to subscribe to.

Example:

~~~java
@Bean
Consumer<Flux<OrderEvent>> auditOrders() {
    return orders -> orders
        .doOnNext(this::audit)
        .subscribe();
}
~~~

According to Spring Cloud Function / Spring Cloud Stream documentation, if you explicitly declare `Consumer<Flux<?>>`, you must subscribe to the input `Flux`. However, doing so forces the application to manage subscription, error handling, and cancellation itself.

### 9.1. Example with Error Handler When Self-Subscribing

~~~java
@Bean
Consumer<Flux<OrderEvent>> auditOrders() {
    return orders -> orders
        .doOnNext(this::audit)
        .subscribe(
            ignored -> { },
            error -> log.error("Audit stream failed", error)
        );
}
~~~

This illustrates the special case. Errors inside this subscription no longer flow through an output publisher that the framework can observe directly like `Function<Flux<T>,Mono<Void>>`.

### 9.2. When Should You Use Consumer<Flux<T>>?

Use it only when you have a clear reason to own the subscription inside the consumer. Clarify:

- Who holds the `Disposable`?
- Who disposes it on application shutdown?
- Where are errors routed?
- Where are retries and cancellation managed?
- Could the subscription be created repeatedly?
- Is there a risk of attaching multiple subscribers to the same source?

For sinks in Spring Cloud Stream, `Function<Flux<T>,Mono<Void>>` is normally clearer and easier to test.

## 10. Do Not Subscribe Inside a Reactive Function

A reactive function should connect an input publisher to an output publisher:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders
        .filter(this::isValid)
        .concatMap(orderService::process);
}
~~~

Avoid:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> {
        orders
            .filter(this::isValid)
            .concatMap(orderService::process)
            .subscribe();

        return Flux.empty();
    };
}
~~~

Problems with the second approach:

1. Creates a subscription detached from the output publisher.
2. Framework receives none of the result data.
3. Errors may bypass normal adapter/binder error handling.
4. Downstream cancellation does not necessarily cancel the inner subscription.
5. Retries can spin up a fresh pipeline while the old subscription stays alive.
6. Side effects may run multiple times if multiple subscriptions occur.
7. Tests checking the returned publisher see an empty stream while background side effects run unseen.

**Rule:** in reactive `Function`s, return the composed publisher; let the caller or adapter at the boundary subscribe.

## 11. Direct Callers Must Subscribe to the Returned Publisher

When invoking the function from ordinary Java code:

~~~java
@SuppressWarnings("unchecked")
Function<Flux<OrderEvent>, Flux<OrderReceipt>> function =
    (Function<Flux<OrderEvent>, Flux<OrderReceipt>>) catalog.lookup("processOrders");

Flux<OrderReceipt> output =
    function.apply(Flux.fromIterable(batch));
~~~

Merely storing `output` without a subscriber leaves the pipeline unexecuted.

In a unit test:

~~~java
StepVerifier.create(output)
    .expectNextMatches(receipt ->
        receipt.orderId().equals("ORD-101")
    )
    .verifyComplete();
~~~

`verifyComplete()` triggers subscription and awaits completion. In reactive application code, callers normally compose that publisher into a response or larger pipeline rather than subscribing at every intermediate layer.

### 11.1. Do Not Subscribe Twice Accidentally

~~~java
Flux<OrderReceipt> output = function.apply(input);

output.subscribe(this::publishReceipt);
return output;
~~~

If the caller/framework also subscribes to the returned publisher, two subscriptions occur. For cold publishers, upstream runs twice and duplicates side effects.

Choose one clear consumption path: return the publisher to the framework, or subscribe at a standalone application boundary.

## 12. HTTP Adapter: Response Lifecycle Drives Subscription

When a reactive function is exposed over HTTP, the web adapter hands the publisher to the HTTP response layer. The web runtime subscribes to write the response body as the client reads it.

Example:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> processOrders() {
    return orders -> orders.map(this::toReceipt);
}
~~~

When invoked via the HTTP adapter, do not call `subscribe()` inside the function. The adapter wires the request body and response publisher per endpoint mapping.

### 12.1. Why Direct Function Calls in Tests Differ from HTTP Calls

- Unit tests call `function.apply(input)` and must subscribe to the publisher.
- HTTP integration tests send requests; the adapter creates and subscribes to the response pipeline.
- If the client disconnects, the subscription can be cancelled.
- If the endpoint never receives a request, the reactive function has not been triggered.

### 12.2. An HTTP Request Body Does Not Guarantee Elements

A request may arrive with an empty body, wrong `Content-Type`, or unmappable payload. A subscriber exists, yet the source emits no events as expected.

Check separately:
- Is the HTTP route exported?
- Does the request hit the right function?
- Was the body deserialized?
- Does the publisher emit `onNext`?
- Does the client read the response body completely?

Do not blame every missing log on a missing subscription.

## 13. Spring Cloud Stream: Binder Connects Reactive Streams

Spring Cloud Stream uses Spring Cloud Function to declare sources, processors, and sinks.

Processor example:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
~~~

Configuration:

~~~properties
spring.cloud.function.definition=uppercase
spring.cloud.stream.bindings.uppercase-in-0.destination=words-in
spring.cloud.stream.bindings.uppercase-out-0.destination=words-out
~~~

Conventional default bindings:

- `uppercase-in-0` is input.
- `uppercase-out-0` is output.

When the binder connects destinations, the framework establishes subscriptions linking the source stream to the function and output stream. The reactive function runs once at initialization to wire the publisher into the pipeline.

### 13.1. No Subscription Exists with Only a Bean and No Adapter

If the app has only:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
~~~

without Spring Cloud Stream, the web adapter, or a direct caller, nothing automatically consumes the publisher. Having a bean does not create a message source or target.

### 13.2. Verify Binding Names and Destinations

| Component | Example | What to verify |
| --- | --- | --- |
| Function definition | `uppercase` | Right bean selected |
| Input binding | `uppercase-in-0` | Bound to destination |
| Input destination | `words-in` | Producer actually sends messages |
| Output binding | `uppercase-out-0` | Has a target |
| Output destination | `words-out` | Consumer reads from the right place |

If bindings are misconfigured or the broker has no messages, the pipeline may be subscribed while receiving zero `onNext` signals.

## 14. Reactive Function Is a Stream Initialization Function in Stream

In Spring Cloud Stream, reactive functions differ from imperative handlers:

- An imperative function is a message handler; for N messages, the function runs N times.
- A reactive function runs once at startup to connect user processing code to the binder's source/target streams.
- Once connected, event processing happens through reactive APIs and subscription lifecycles.

~~~mermaid
flowchart LR
    A["Binder input source"] --> B["Subscription"]
    B --> C["Flux<OrderEvent>"]
    C --> D["Reactive Function"]
    D --> E["Flux<OrderReceipt>"]
    E --> F["Binder output target"]
~~~

This explains why a log at the top of the function method prints once at startup, whereas logs inside `doOnNext` print once per event.

### 14.1. Distinguish Assembly Logs from Event-Processing Logs

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    log.info("Creating reactive function");

    return values -> {
        log.info("Connecting reactive pipeline");

        return values.map(value -> {
            log.info("Processing value {}", value);
            return value.toUpperCase();
        });
    };
}
~~~

In Spring Cloud Stream, the first two logs relate to creation/assembly; the log inside `map` executes only when subscribed and items arrive.

Do not cite "function method called once" as proof that the stream processed only one event.

## 15. Supplier<Flux<T>>: Stream Sources Also Need Subscriptions

Reactive Supplier:

~~~java
@Bean
Supplier<Flux<String>> messages() {
    return () -> Flux.interval(Duration.ofSeconds(1))
        .map(sequence -> "event-" + sequence);
}
~~~

In Spring Cloud Stream, a reactive `Supplier` is typically invoked once to create a continuous stream. The binder subscribes to the publisher to receive messages.

Calling `Supplier.get()` and returning a `Flux` does not mean events have already started flowing. Sources like `Flux.interval` begin emitting only once subscribed to.

### 15.1. Do Not Subscribe Inside a Supplier

Wrong:

~~~java
@Bean
Supplier<Flux<String>> messages() {
    return () -> {
        Flux<String> stream = createEvents();
        stream.subscribe(this::send);
        return Flux.empty();
    };
}
~~~

This detaches emission from the binder-managed output binding. Return the publisher directly:

~~~java
@Bean
Supplier<Flux<String>> messages() {
    return this::createEvents;
}
~~~

### 15.2. Continuous Reactive Suppliers Differ from Imperative Suppliers

| Supplier | Typical behavior in Spring Cloud Stream |
| --- | --- |
| `Supplier<T>` | Poller invokes `get()` periodically to produce each message |
| `Supplier<Flux<T>>` | Invoked once to build a continuous stream; binder subscribes |
| `@PollableBean Supplier<Flux<T>>` | Finite reactive supplier marked so polling frameworks can re-invoke it |

Do not apply imperative `Supplier` polling rules to every reactive `Supplier`.

## 16. Finite Reactive Suppliers: Need a Polling Mechanism

Sometimes a `Supplier` returns a finite stream, such as reading a batch from a database:

~~~java
@Bean
Supplier<Flux<OrderEvent>> pendingOrders() {
    return () -> orderRepository.findPendingOrders();
}
~~~

This publisher emits some events and completes. If invoked only once at startup, once finished it will not automatically fetch a fresh batch.

Spring Cloud Function provides the `@PollableBean` marker to indicate a reactive `Supplier` produces a finite stream and may need repeated polling. Spring Cloud Function itself does not implement polling behavior for this annotation; integration frameworks like Spring Cloud Stream supply the polling mechanism.

Example:

~~~java
@PollableBean(splittable = true)
public Supplier<Flux<OrderEvent>> pendingOrders() {
    return () -> orderRepository.findPendingOrders();
}
~~~

### 16.1. PollableBean and splittable

In Spring Cloud Stream, `@PollableBean` indicates that a reactive `Supplier` should be polled. The `splittable` attribute controls how the resulting stream is emitted:

- `splittable = true`: splits each item into an individual message; this is the default per current Spring Cloud Stream docs.
- `splittable = false`: sends the publisher as a single stream result instead of splitting item by item.

Choose based on your output contract and binder.

### 16.2. Default Poller and Configuration

Spring Cloud Stream provides a default poller. Current documentation describes a default fixed delay of 1000 ms.

~~~properties
spring.integration.poller.fixed-delay=5000
spring.integration.poller.max-messages-per-poll=1
~~~

This example adjusts the polling interval and max messages per poll. For a specific binding, you can use the per-binding poller prefix:

~~~properties
spring.cloud.stream.bindings.pendingOrders-out-0.producer.poller.fixed-delay=5000
~~~

Verify the exact binding name and configuration for your version.

### 16.3. Do Not Use PollableBean to Force Arbitrary Unsubscribed Fluxes to Run

`@PollableBean` is intended for finite reactive `Supplier`s integrated with a polling mechanism. It is not a generic annotation to make arbitrary `Flux` instances run automatically.

## 17. Reactive Consumers: Why Does Void Return Easily Lose Subscription?

A `Consumer<T>` returns `void`. For imperative inputs, the framework invokes the consumer per event and needs no output publisher.

However, `Consumer<Flux<T>>` accepts a publisher and returns `void`. The framework gets no resulting publisher to subscribe to.

Spring Cloud Stream recommends using:

~~~java
Function<Flux<OrderEvent>, Mono<Void>>
~~~

instead of:

~~~java
Consumer<Flux<OrderEvent>>
~~~

Correct example:

~~~java
@Bean
Function<Flux<OrderEvent>, Mono<Void>> storeOrders(
        OrderService orderService) {

    return orders -> orders
        .concatMap(orderService::persist)
        .then();
}
~~~

If you still declare an explicit reactive `Consumer`, you must subscribe to the input `Flux` and manage its lifecycle yourself. This is a deliberate exception, not the default pattern.

## 18. Composition Can Produce a Reactive Consumer with Nothing Subscribing

Spring Cloud Function supports composing reactive and imperative functions, though you must watch the resulting type.

For instance, composing a reactive function with an imperative `Consumer` can produce a reactive `Consumer`. Because `Consumer` returns `void`, there is no output publisher for the framework to subscribe to.

Avoid this pitfall when designing stream compositions.

### 18.1. How to Fix It

- Replace the consumer with `Function<Flux<T>,Mono<Void>>` to return a completion publisher.
- Or switch processing to an imperative function/consumer if the framework invokes per event.
- Or self-subscribe inside a reactive `Consumer` only when you intentionally own the subscription and handle errors/cancellation.

### 18.2. Check the Composed Type

Do not inspect only individual functions. Determine the final composed type:

| Steps | Resulting type |
| --- | --- |
| `Function<Flux<T>,Flux<R>>` | Reactive `Function` |
| `Function<Flux<T>,Mono<Void>>` | Reactive completion function |
| `Function<Flux<T>,...>` + imperative `Consumer` | Can become a reactive `Consumer` |
| `Supplier<Flux<T>>` + `Function<Flux<T>,Flux<R>>` | Check reactive supplier/function contract and adapter subscription |

If the result is `Consumer<Flux<T>>`, check who will subscribe to the input publisher.

## 19. Cold vs. Hot Publishers: Subscribed Yet Still Missing Events

Not all publishers respond identically to subscriptions.

### 19.1. Cold Publisher

A cold publisher generates fresh data for each subscription:

~~~java
Flux<String> cold = Flux.defer(() ->
    Flux.just("one", "two", "three")
);
~~~

Each subscriber can receive the full sequence. Without a subscription, the source emits nothing.

### 19.2. Hot Publisher

A hot publisher can emit independently of subscribers. Late subscribers may receive only events emitted after subscribing.

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().directBestEffort();

Flux<String> hot = sink.asFlux();

sink.tryEmitNext("before-subscribe");

hot.subscribe(System.out::println);

sink.tryEmitNext("after-subscribe");
~~~

In this direct multicast setup, a new subscriber misses events emitted before subscription.

### 19.3. Choosing the Right Source Type

| Requirement | Preferred choice |
| --- | --- |
| Each subscriber processes the full dataset anew | Cold publisher |
| Share live events among active subscribers | Hot publisher / multicast |
| Late subscribers need bounded history | Bounded replay/cache |
| Create fresh source per subscription | `defer` |
| Long-lived stream from an event source | Hot publisher or lifecycle-managed connector |

### 19.4. share and Multiple Subscriptions

`share()` can share one source across subscribers after the first subscription begins. However, late subscribers do not by default receive past history.

Do not sprinkle `share()` as a way to "turn on" a publisher without understanding subscriber counts, connection timing, and replay semantics.

## 20. Multiple Subscriptions Can Cause Duplicate Processing

With a cold publisher:

~~~java
Flux<OrderEvent> orders = orderRepository.findAllPending();

orders.subscribe(this::process);
orders.subscribe(this::process);
~~~

Two subscriptions can run two queries and process the same records twice.

Similarly, if a function self-subscribes and the framework also subscribes to the returned publisher, side effects can run twice.

### 20.1. Count Subscriptions

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Flux<Integer> source = Flux.defer(() -> {
    subscriptions.incrementAndGet();
    return Flux.just(1, 2, 3);
});
~~~

Each subscription increments the counter once. Use this technique in tests to catch unintended extra subscriptions.

### 20.2. Idempotency Is Still Essential

In event-driven processing, retries or multiple subscriptions can cause the same event to be processed again. Use event IDs, idempotency keys, or unique constraints to protect side effects. Do not rely on `cache()` or `share()` as a substitute for business-level deduplication.

## 21. Source Is Subscribed To Yet Emits No Data

A successful subscription does not guarantee the source emits `onNext`.

| Source/pipeline | Behavior |
| --- | --- |
| `Flux.empty()` | Completes immediately, zero items |
| `Flux.never()` | Emits nothing, never completes, never errors |
| `Flux.interval(...)` | Emits ticks only after subscription and on schedule |
| `filter(...)` | May filter out every element |
| `take(0)` | Completes without emitting items |
| `Flux.create(...)` | Callback must emit data or complete the sink |
| `onErrorResume(...)` | May replace errors with an empty publisher |
| `Mono<Void>` | Completes without emitting a payload |

### 21.1. Filter Drops Everything

~~~java
Flux<OrderEvent> accepted = incoming
    .filter(order -> order.total().signum() > 0);
~~~

If all orders have zero or negative totals, the pipeline subscribes normally yet zero events pass the filter.

Add metrics/counters before and after filters to distinguish an empty source from an overly strict filter.

### 21.2. Flux.create Emits No Signals

~~~java
Flux<String> source = Flux.create(sink -> {
    // Neither sink.next(...), sink.error(...), nor sink.complete() is called.
});
~~~

The publisher has a subscriber yet emits nothing and never finishes. Check whether source callbacks, listeners, emitters, or adapters actually push data into the sink.

### 21.3. Mono<Void> Completes Without Payload

When using `Function<Flux<T>,Mono<Void>>`, seeing zero output events is by design. Observe side effects, completion, and metrics rather than waiting for `onNext`.

## 22. Errors and Cancellation Can Stop Streams Early

A publisher may have subscribed yet halted due to an error:

~~~java
Flux<OrderReceipt> receipts = orders
    .map(this::normalize)
    .concatMap(orderService::process)
    .doOnError(error ->
        log.error("Order processing failed", error)
    );
~~~

`onError` is a terminal signal; afterward, the publisher stops emitting items.

### 22.1. Distinguish Observing Errors from Recovering from Errors

~~~java
Flux<OrderReceipt> receipts = orders
    .concatMap(orderService::process)
    .doOnError(error -> log.error("Failed", error))
    .onErrorResume(error -> fallbackOrders());
~~~

- `doOnError` only observes the error.
- `onErrorResume` switches the remainder of the sequence to another publisher.
- `retryWhen` re-subscribes according to policy.

Do not use `onErrorComplete` or empty fallbacks to hide errors while diagnosing; that can make a pipeline appear to "finish cleanly" while dropping data.

### 22.2. Cancellation

A subscription can be cancelled when:

- An HTTP client disconnects.
- A binder stops or a consumer shuts down.
- `take(n)` has collected enough elements.
- `Disposable.dispose()` is called.
- A test calls `thenCancel()`.
- Downstream is no longer interested in results.

Use `doOnCancel` to tell whether a stream stopped due to cancellation rather than waiting indefinitely for new events.

### 22.3. Retries Can Replay Side Effects

`retryWhen` re-subscribes upstream. If the source is cold and operators perform side effects, they can run again. Guarantee idempotency and place retry boundaries around the right operations.

## 23. Backpressure: The Subscriber May Not Have Requested Items Yet

Reactive Streams uses demand so subscribers regulate emission speed.

A custom subscriber can subscribe without requesting data. Until it does, the source is not asked to emit items.

In tests, you can inspect controlled demand:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(1)
    .expectNext(2)
    .thenCancel()
    .verify();
~~~

This test starts with 0 demand, requests items one by one, and finally cancels. It illustrates that subscription and demand are related yet distinct concepts.

### 23.1. A Silent Binder Is Not Always Missing Demand

When using a non-reactive binder, the adapter may wrap messages into a publisher without providing full reactive transport backpressure semantics. Verify which binder is running and whether the source actually has messages.

## 24. Do Not Use block to Mask a Missing Subscription

Calls such as:

~~~java
String value = mono.block();
OrderEvent last = flux.blockLast();
~~~

perform subscription and wait for results. They can be handy in tests or imperative adapters with explicit blocking boundaries, yet they are not the default fix inside reactive functions.

### 24.1. Why Is Blocking Inside a Pipeline Dangerous?

- Blocks event-loop threads.
- Reduces concurrency.
- Can cause deadlocks when blocking on non-blocking-safe schedulers.
- Negates non-blocking benefits.
- Hides the fact that the publisher ought to be composed and returned.

### 24.2. Use Operators Instead of block

Wrong:

~~~java
orders.map(order -> orderService.process(order).block());
~~~

Right:

~~~java
orders.flatMap(orderService::process);
~~~

If processing order must be preserved:

~~~java
orders.concatMap(orderService::process);
~~~

## 25. Schedulers Do Not Replace Subscriptions

`subscribeOn` and `publishOn` are often mistaken for making a stream run automatically.

~~~java
Flux<OrderReceipt> result = orders
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .flatMap(orderService::process);
~~~

This is still just a publisher. A caller or framework must still subscribe.

### 25.1. When You Need to Call a Blocking API

For legacy blocking services, isolate the blocking call:

~~~java
Mono<OrderReceipt> processBlocking(OrderEvent event) {
    return Mono.fromCallable(() -> legacyService.process(event))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Do not call `subscribe()` inside this helper. Return the `Mono` so callers compose it and manage subscription.

### 25.2. Do Not Spawn Manual Threads per Event

Using `new Thread(...)` or unmanaged executors to force side effects detaches work from the stream lifecycle. Prefer Reactor schedulers, reactive clients, and binder-managed subscriptions.

## 26. Managing Manual Subscriptions When Genuinely Required

Some standalone components must connect a publisher to a subscriber themselves. In that case, the subscription is a managed resource.

~~~java
@Component
class ExternalStreamBridge {

    private final ExternalEventSource source;
    private Disposable subscription;

    ExternalStreamBridge(ExternalEventSource source) {
        this.source = source;
    }

    @PostConstruct
    void start() {
        this.subscription = source.events()
            .subscribe(
                this::handle,
                error -> log.error("External stream failed", error)
            );
    }

    @PreDestroy
    void stop() {
        if (subscription != null && !subscription.isDisposed()) {
            subscription.dispose();
        }
    }

    private void handle(ExternalEvent event) {
        // Process a received event.
    }
}
~~~

This example shows clear ownership:

- The component creates the subscription on lifecycle start.
- It retains the `Disposable` for inspection/cancellation.
- It handles subscription errors.
- It disposes on Spring context shutdown.

Inside Spring Cloud Function / Spring Cloud Stream reactive `Function` beans, let the adapter/binder own the subscription instead of opening a second subscription inside the bean.

## 27. Testing Reactive Functions with StepVerifier

`StepVerifier` subscribes to the publisher and asserts signals in order.

Function:

~~~java
Function<Flux<Integer>, Flux<Integer>> doubleNumbers =
    numbers -> numbers.map(number -> number * 2);
~~~

Test:

~~~java
@Test
void functionProcessesValuesWhenSubscribed() {
    Flux<Integer> result =
        doubleNumbers.apply(Flux.just(1, 2, 3));

    StepVerifier.create(result)
        .expectNext(2)
        .expectNext(4)
        .expectNext(6)
        .verifyComplete();
}
~~~

`verifyComplete()` triggers subscription and waits for completion. Merely building `result` without calling a terminal verifier leaves the pipeline unexecuted.

### 27.1. Test Detecting Missing Subscription

~~~java
@Test
void noSideEffectBeforeSubscription() {
    AtomicInteger processed = new AtomicInteger();

    Flux<Integer> pipeline = Flux.range(1, 3)
        .doOnNext(value -> processed.incrementAndGet());

    assertThat(processed.get()).isZero();

    StepVerifier.create(pipeline)
        .expectNext(1, 2, 3)
        .verifyComplete();

    assertThat(processed.get()).isEqualTo(3);
}
~~~

This test confirms side effects run only after `StepVerifier` subscribes.

### 27.2. Testing Reactive Consumer Function<Flux<T>,Mono<Void>>

~~~java
@Test
void consumerCompletesAfterAllEventsArePersisted() {
    List<Integer> stored = new ArrayList<>();

    Function<Flux<Integer>, Mono<Void>> consumer =
        values -> values
            .concatMap(value -> Mono.fromRunnable(
                () -> stored.add(value)
            ))
            .then();

    StepVerifier.create(consumer.apply(Flux.just(1, 2, 3)))
        .verifyComplete();

    assertThat(stored).containsExactly(1, 2, 3);
}
~~~

This is an essential test: publisher completion represents that every event has finished processing.

## 28. Testing Errors, Cancellation, and Backpressure

### 28.1. Error Test

~~~java
StepVerifier.create(
        Flux.just(1, 2)
            .concatWith(Mono.error(
                new IllegalStateException("source failed")
            ))
    )
    .expectNext(1, 2)
    .expectErrorMessage("source failed")
    .verify();
~~~

Verifies the error signal is emitted once the subscriber drives the pipeline.

### 28.2. Cancellation Test

~~~java
StepVerifier.create(Flux.interval(Duration.ofMillis(100)))
    .expectNext(0L)
    .thenCancel()
    .verify();
~~~

`thenCancel()` verifies cancellation. Combine `doOnCancel` with a counter to assert cleanup.

### 28.3. Demand Test

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
~~~

This proves the source need not emit everything the moment a subscriber attaches; demand governs how many items are requested.

## 29. Diagnosing in Spring Cloud Stream

When a reactive function receives no messages, check in order:

1. Does the function bean exist with the right generic signature?
2. Does `spring.cloud.function.definition` pick the right name?
3. Do input/output bindings follow expected naming conventions?
4. Are destination and binder configured properly?
5. Is the producer sending messages to that destination?
6. Were the consumer group and subscription created?
7. Was the reactive function invoked to wire the stream at startup?
8. Is `doOnSubscribe` placed properly to confirm subscription?
9. Are demand and `onNext` happening?
10. Did filters or validation drop every item?
11. Did `onError` or cancellation halt the pipeline?
12. Does the output binding have a valid destination and downstream consumer?

### 29.1. Sample Binding Configuration

~~~properties
spring.cloud.function.definition=processOrders
spring.cloud.stream.bindings.processOrders-in-0.destination=orders-in
spring.cloud.stream.bindings.processOrders-in-0.group=order-service
spring.cloud.stream.bindings.processOrders-out-0.destination=orders-out
~~~

The consumer group determines delivery/subscription semantics per binder. An app using a different group may see a different message flow than the one you are observing.

### 29.2. Inspect Startup Logs

Look for log entries covering:

- Selected function definition.
- Created input/output bindings.
- Binder connections and destinations.
- Consumer groups.
- Reactive function subscription/lifecycle.
- Exceptions raised before the binder connected.

If startup logs confirm bindings were created yet zero `onNext` signals arrive, inspect the producer, destination, deserializer, and filters before blaming a missing subscription.

## 30. Symptom and Action Table

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| No logs inside `map` | Missing subscription | `doOnSubscribe`, caller/adapter |
| Bean exists, no events arrive | Missing adapter/source | Function definition and bindings |
| Subscribed, zero `onNext` | Empty source, unemitted sink, or demand 0 | `doOnRequest`, source callbacks |
| `onNext` before filter, none after | Filter drops all items | Counters before/after filter |
| Function returns `Flux`, caller sees no output | Caller does not subscribe/consume | HTTP adapter or `StepVerifier` |
| `Consumer<Flux<T>>` does not run | Consumer never subscribed | Switch to `Function<Flux<T>,Mono<Void>>` |
| `Supplier<Flux<T>>` emits only one batch | Finite stream created once | Polling and `@PollableBean` |
| Event processed twice | Multiple subscriptions | `doOnSubscribe`, idempotency |
| Stream stops after one event | Error signal or cancellation | `doOnError`, `doOnCancel` |
| No output yet `Mono<Void>` completes | Consumer emits no payload by design | Check side effects / completion |
| Slow output | Backpressure or slow source | `doOnRequest`, schedulers, source latency |
| Test skips operators | Forgot to call `verify()` | `StepVerifier` terminal assertion |
| `subscribeOn` configured, still silent | Scheduler does not create a subscription | Caller/adapter |
| `block()` hangs the app | Blocking inside reactive pipeline | Remove `block`, compose publishers |
| Hot stream misses initial events | Late subscriber | Hot/cold, replay, source lifecycle |

## 31. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Creating a `Flux` starts processing data." | Creating a publisher only describes the source/pipeline; subscription activates it. |
| "`map` and `filter` are terminal operations." | They build new publishers and do not subscribe. |
| "`doOnNext` executes side effects when declared." | Callbacks run only when items are emitted. |
| "`collectList()` fetches data on its own." | It returns `Mono<List<T>>`; subscription is still required. |
| "`then()` subscribes to the `Flux`." | `then()` returns `Mono<Void>` and does not subscribe. |
| "`subscribeOn` makes a stream run automatically." | It only picks the scheduler when subscription happens. |
| "Reactive `Function`s should call `subscribe()` inside the method." | Normally return the publisher for adapters/binders to manage. |
| "`Consumer<Flux<T>>` works just like `Function<Flux<T>,Mono<Void>>`." | `Consumer` returns `void`, leaving the framework no output publisher to subscribe to. |
| "Having a bean in `FunctionCatalog` means a subscriber exists." | Catalog registration and subscription are separate things. |
| "Spring Cloud Stream invokes a reactive function per event." | Reactive functions run once to wire the stream. |
| "Reactive `Supplier`s are always polled every second." | Continuous reactive `Supplier`s run once; finite ones need polling setup. |
| "`@PollableBean` implements polling inside SCF." | It is a marker; integration frameworks like Stream provide polling behavior. |
| "A subscription always receives full hot-stream history." | Hot publishers may send only new events to late subscribers. |
| "Subscribing twice has no effect." | Cold publishers can re-run the source and side effects twice. |
| "Having a subscription guarantees `onNext`." | Source may be empty/never, filtered out, not emitting yet, or awaiting demand. |
| "No output means the stream didn't run." | `Mono<Void>` completes validly without emitting payloads. |
| "`block()` is how to fix reactive pipelines." | `block()` subscribes yet blocks threads and risks deadlocks. |
| "A reactive `Consumer` is always auto-subscribed by the binder." | `Consumer<Flux<T>>` returns `void`; self-subscribe or switch to reactive `Function`. |
| "Errors inside a nested `subscribe()` are tracked like the output `Flux`." | Fire-and-forget subscriptions detach errors and cancellation from the main pipeline. |

## 32. Checklist Before Concluding a Subscription Is Missing

### 32.1. Publisher and Caller

- [ ] Is an actual source publisher created?
- [ ] Are operators chained onto the returned publisher?
- [ ] Were any inner publishers dropped inside callbacks?
- [ ] Does the caller subscribe or compose the publisher further?
- [ ] Are there zero unintended duplicate subscriptions?
- [ ] Are demand and source emissions active?

### 32.2. Spring Cloud Function/Stream

- [ ] Does the function signature match the intended imperative/reactive model?
- [ ] Does a reactive `Function` return `Flux`/`Mono` to the framework?
- [ ] Does `Consumer<Flux<T>>` subscribe explicitly, or was it converted to `Function<Flux<T>,Mono<Void>>`?
- [ ] Does `spring.cloud.function.definition` pick the right bean?
- [ ] Did the binder create bindings and connect destinations?
- [ ] Is a reactive `Supplier` continuous or finite?
- [ ] If finite, is a suitable polling mechanism configured?
- [ ] Are startup initialization logs distinguished from per-event processing?

### 32.3. Lifecycle and Errors

- [ ] Are `onError`/`onComplete`/`onCancel` observed?
- [ ] Are manual `Disposable` handles retained and disposed cleanly?
- [ ] Can retries duplicate side effects?
- [ ] Is backpressure making the source wait for demand?
- [ ] Could a hot publisher have emitted before the subscriber attached?
- [ ] Do `StepVerifier` tests invoke a terminal `verify` method?

## 33. Self-Assessment Questions

1. What does a `Flux` represent, and why is it not an already-executed `List`?
2. How do assembly and subscription differ?
3. Why does `map` not trigger the source?
4. Which signals does a subscriber send to start receiving data?
5. What role does `request(n)` play?
6. Does `doOnNext` subscribe automatically?
7. Why does `collectList()` not execute the pipeline by itself?
8. Do `publishOn` and `subscribeOn` replace subscription?
9. Why should a reactive `Function` return its publisher instead of calling `subscribe()` internally?
10. In Spring Cloud Stream, how many times is a reactive `Function` invoked, and when?
11. Why does `Consumer<Flux<T>>` require manual subscription?
12. Why is `Function<Flux<T>,Mono<Void>>` a better choice for reactive sinks?
13. How does `then()` differ from `subscribe()`?
14. When must a direct caller subscribe to a function's output?
15. Why can subscribing twice duplicate side effects?
16. How do cold publishers and hot publishers differ?
17. Why can a hot publisher cause late subscribers to miss events?
18. How does a continuous `Supplier<Flux<T>>` differ from a finite supplier?
19. What role does `@PollableBean` play, and which framework performs the polling?
20. Why can a subscription receive zero `onNext` signals?
21. How can `filter` make a stream appear dead?
22. How do error signals and cancellation differ?
23. Why can retries re-execute side effects?
24. What does `StepVerifier.verifyComplete()` trigger?
25. How do you verify the binder created the input binding and consumer group?
26. Why can `Mono<Void>` completing with zero output payload still be completely valid?
27. When is manual `Disposable` management necessary?
28. Which logs let you distinguish a missing subscription from a silent source?

## 34. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — reactive `Supplier`, `Function`, `Consumer`; invocation semantics; `Consumer<Flux<?>>` subscription requirement; `@PollableBean`.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — binder wiring, reactive `Consumer`, `Function<Flux<?>,Mono<Void>>`, `Supplier` polling, `PollableBean`, and poller properties.
- [Spring Cloud Stream — Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html) — reactive functions as initialization functions; observability differences between imperative and reactive streams.
- [Project Reactor — Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html) — assembly, subscribe, request, backpressure, and Reactive Streams signals.
- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) — cold/hot semantics, late subscribers, `share`, and replay.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier`, demand, and cancellation.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — Publisher, Subscriber, Subscription, and backpressure contracts.

Examples use Java 17+, Project Reactor, and current Spring Cloud Function / Spring Cloud Stream APIs. Binding names, pollers, binder capabilities, and how adapters manage subscriptions can vary by BOM/version. Verify the exact runtime adapter, signatures, and dependencies of your deployed application.

**Takeaway:** A `Flux` merely describes a stream of data. Operators wire the pipeline without running it; subscription and demand trigger data emission. In reactive `Function`s, return the publisher so adapters/binders manage subscription. For reactive consumers, prefer `Function<Flux<T>,Mono<Void>>` so the framework gets a completion publisher; use `Consumer<Flux<T>>` only when actively subscribing and managing errors/cancellation yourself. For reactive suppliers, distinguish continuous streams subscribed once from finite streams requiring polling. When diagnosing, observe subscription, request, `onNext`, `onError`, completion, and cancellation; finally confirm sources/bindings carry real data using `StepVerifier` or integration tests.
