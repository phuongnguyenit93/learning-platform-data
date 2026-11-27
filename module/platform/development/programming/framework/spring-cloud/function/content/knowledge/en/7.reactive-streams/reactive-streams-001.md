# Mono, Flux, and Reactive Function Signatures in Spring Cloud Function

## 1. Why Does Spring Cloud Function Need Mono and Flux?

Spring Cloud Function allows packaging business logic into Java functions such as `Supplier`, `Function`, and `Consumer`, and exposing them through `FunctionCatalog` so adapters can invoke them via HTTP, event systems, or serverless environments. When a problem involves continuously arriving data, asynchronous I/O, or multiple results over time, reactive signatures using Project Reactor's `Mono` and `Flux` let functions describe a **processing stream** instead of waiting for each operation to complete.

For example, a system receiving order events can inspect each order as it arrives, call an asynchronous risk-check service, and emit results to the output stream. The inspection logic still resides in the `Function` bean; the message source and output destination are decided by the adapter.

Important point: **a `Flux<T>` is a description of a stream of `T` elements, not a pre-loaded `List<T>`**. A `Mono<T>` is also a publisher, even though it emits at most one value. Using reactive types does not automatically turn blocking code into non-blocking code; that property depends on both the operations inside the function and the I/O libraries used.

## 2. Reactor Foundations: Mono, Flux, and Stream Signals

Reactor implements the Reactive Streams specification through `Publisher`, `Subscriber`, and `Subscription`. Once subscribed to, a publisher can emit the following signals:

- `onNext(value)`: a new element is available;
- `onComplete()`: normal completion;
- `onError(error)`: termination due to an error.

`onComplete` and `onError` are mutually exclusive terminal signals. After a terminal signal, the publisher emits no further elements.

| Concept | Max elements per subscription | Suitable use cases |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | A single lookup result, single HTTP response, completion confirmation |
| `Flux<T>` | 0 to N | Event streams, multiple records, result sets, or continuous streams |
| `Mono<Void>` | Emits no business value | Signaling completion or error of an asynchronous task |
| `Flux<Message<T>>` | 0 to N messages | Processing payloads together with metadata such as correlation IDs and routing headers |

Basic Reactor examples:

~~~java
Mono<String> customer = Mono.just("C-42");
Flux<String> orders = Flux.just("O-1", "O-2", "O-3");

Flux<String> oneAsFlux = customer.flux();
Mono<List<String>> allOrders = orders.collectList();
Mono<String> firstOrder = orders.next();
~~~

`collectList()` is only appropriate when the stream is finite and its size is bounded, because it must buffer elements in memory before emitting the list. If used on an infinite stream, `Mono<List<T>>` will never complete. `next()` takes the first element and cancels the subscription for the remainder when possible.

**Do not use `null` as an element or the result of `map`.** Reactor forbids `null` in `onNext` signals. Use `Mono.empty()` when there is no result, or operators like `filter`/`flatMap` when elements need to be dropped.

### 2.1. Publishers Usually Only Run When Subscribed To

Most publishers created with `just`, `fromIterable`, `map`, and `flatMap` are *cold*: each subscription can trigger an independent execution pass. A hot source, such as one receiving events via `Sinks.Many`, can emit data without waiting for a new subscriber; late subscribers may miss earlier events depending on configuration.

~~~java
Flux<Integer> pipeline = Flux.just(1, 2, 3)
    .map(x -> x * 10); // Only describes the transformation

// Once a subscriber subscribes, the pipeline emits 10, 20, 30.
pipeline.subscribe(System.out::println);
~~~

The `subscribe()` call above illustrates pure Reactor. **Inside a Spring Cloud Function `Function<Flux<T>, Flux<R>>` bean, you should normally return the publisher so the framework/adapter manages the subscription.** Calling `subscribe()` manually inside a function easily breaks error propagation, cancellation management, and completion tracking.

### 2.2. Backpressure and Cancellation

A subscriber can request a specific number of elements via the `request(n)` mechanism instead of receiving an unbounded flood; this is *backpressure*. A subscriber can also cancel the subscription when results are no longer needed. Reactor operators participate in propagating request and cancel signals, but overall effectiveness still depends on the data source and adapter: a message broker, HTTP client, or external system does not necessarily throttle according to every `request(n)` signal.

Therefore, limiting I/O task concurrency with `flatMap(mapper, concurrency)` remains necessary to avoid having too many in-flight requests. Backpressure should not be treated as a guarantee that every external queue is automatically bounded.

## 3. Reactive Function Signatures in Spring Cloud Function

In synchronous programming, a function typically accepts and returns values directly:

~~~java
Function<String, String> normalize = text -> text.trim().toUpperCase();
~~~

In the reactive style, the parameter and/or return value can be a publisher:

| Signature | Meaning | Lifecycle notes |
| --- | --- | --- |
| `Function<Mono<T>, Mono<R>>` | Transforms one asynchronous input into at most one result | Suitable when the adapter contract represents a single value |
| `Function<Flux<T>, Flux<R>>` | Transforms a stream of `T` into a stream of `R` | Can emit 0, 1, or many `R` for each `T` |
| `Function<Flux<T>, Mono<R>>` | Reduces/aggregates a stream into at most one `R` | Usually emits the result only after the input stream completes |
| `Supplier<Flux<T>>` | Provides a publisher as a data source | Number of supplier invocations and subscriptions depends on the adapter |
| `Supplier<Mono<T>>` | Provides a publisher of at most one value | May be empty or fail |
| `Consumer<Flux<T>>` | Receives a publisher to perform side effects | Does not return a publisher with completion/error signals to the caller; requires careful subscription management |
| `Function<Flux<T>, Mono<Void>>` | Performs an asynchronous task over a stream and returns a completion signal | Useful when the caller/adapter can await publisher completion |

`T` and `R` can be business payload types (`OrderEvent`, `Decision`), or `Message<T>` to carry messages and headers. The function signature provides type information to `FunctionCatalog` and the data conversion mechanism, while the specific adapter determines how each invocation, subscription, and output is packaged.

### 3.1. The Boundary Between “One Element” and “One Stream”

The two functions below have identical transformation logic, yet carry different contracts:

~~~java
Function<String, String> upperOne = String::toUpperCase;

Function<Flux<String>, Flux<String>> upperStream =
    source -> source.map(String::toUpperCase);
~~~

With `upperOne`, the caller passes one `String` and receives one `String`. With `upperStream`, the caller passes a publisher; the function can process multiple elements within **the same subscription**. When using an event adapter that supports continuous streams, do not assume the framework will re-invoke the lambda once per message.

On the other hand, `Mono` does not mean “only one element across the entire application lifecycle”. Each subscription to a cold publisher can re-execute the operation. To prevent duplicate emissions when integrating with a broker, you need idempotency contracts, checkpointing/acknowledgment, and corresponding source management.

### 3.2. Type Constraints in Composition

A chain `a|b` is valid when the logical output of `a` is compatible with the input of `b`. For example:

~~~java
@Bean
Function<Flux<String>, Flux<String>> trimText() {
    return source -> source.map(String::trim);
}

@Bean
Function<Flux<String>, Flux<String>> markText() {
    return source -> source.map(value -> "checked:" + value);
}
~~~

Declare the function definition for the adapter:

~~~properties
spring.cloud.function.definition=trimText|markText
~~~

When the chain is selected, data flows through `trimText` and then `markText`. Spring Cloud Function uses `FunctionCatalog` to look up, wrap, and compose function beans. For complex combinations across synchronous types, `Mono`, `Flux`, or `Message`, verify type compatibility and actual behavior on your adapter version; do not assume every combination preserves invocation counts and message headers unchanged.

## 4. Complete Example: Inspecting an Order Stream

Suppose each order has an ID and an amount. The requirement is to mark orders with a positive amount as accepted, while also providing a standalone function to sum the amounts of a finite stream.

This is a protocol-independent Spring configuration. The example uses `record`, requiring Java 17 or later along with the corresponding Spring Cloud Function and Reactor dependencies.

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderFunctions {

    public record OrderEvent(String orderId, long amount) { }
    public record Decision(String orderId, boolean accepted) { }

    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> checkOrders() {
        return orders -> orders.map(order ->
            new Decision(order.orderId(), order.amount() > 0)
        );
    }

    @Bean
    public Function<Mono<OrderEvent>, Mono<Decision>> checkOneOrder() {
        return oneOrder -> oneOrder.map(order ->
            new Decision(order.orderId(), order.amount() > 0)
        );
    }

    @Bean
    public Function<Flux<OrderEvent>, Mono<Long>> sumAmounts() {
        return orders -> orders
            .map(OrderEvent::amount)
            .reduce(0L, Long::sum);
    }
}
~~~

**Breakdown of each signature:**

1. `checkOrders` takes `Flux<OrderEvent>` and returns `Flux<Decision>`. `map` performs a synchronous transformation per element, preserves order, and creates no separate I/O tasks.
2. `checkOneOrder` takes `Mono<OrderEvent>`. If the input is `Mono.empty()`, the output is also empty; the lambda inside `map` does not run.
3. `sumAmounts` uses `reduce(0L, Long::sum)`. It emits a single sum only when the input completes; for an empty stream, the sum is `0L`. In the case of a continuous event stream without `onComplete`, this function will not emit a final sum.

Example calling the beans directly to observe behavior:

~~~java
OrderFunctions config = new OrderFunctions();

Flux<OrderFunctions.OrderEvent> input = Flux.just(
    new OrderFunctions.OrderEvent("O-100", 120),
    new OrderFunctions.OrderEvent("O-101", 0)
);

Flux<OrderFunctions.Decision> checked =
    config.checkOrders().apply(input);

Mono<Long> total = config.sumAmounts().apply(
    Flux.just(
        new OrderFunctions.OrderEvent("O-100", 120),
        new OrderFunctions.OrderEvent("O-101", 0)
    )
);
~~~

`checked` describes two results: `Decision("O-100", true)` and `Decision("O-101", false)`. `total` describes a single result: `120L`. Neither necessarily executes until there is a subscriber. If two functions share **one** cold publisher, each subscription may re-read the source; on hot sources or sources with side effects, sharing/replay strategies must be designed explicitly.

### 4.1. Need Periodic Aggregation from an Unbounded Stream?

Instead of calling `reduce` on the entire stream, you can split it into windows by count or time and aggregate each window:

~~~java
Function<Flux<Long>, Flux<Long>> sumInWindows = amounts ->
    amounts
        .windowTimeout(100, java.time.Duration.ofSeconds(5))
        .concatMap(window -> window.reduce(0L, Long::sum));
~~~

Each window is processed and emits its own sum. The result remains a `Flux<Long>`, suitable for continuous sources. Choosing window size, empty-window behavior, and latency must be based on actual requirements.

## 5. Supplier, Consumer, and Subscription Ownership

The three patterns—Supplier, Function, and Consumer—keep their familiar roles in reactive programming, but producing and consuming publishers requires clarity on who the final subscriber is.

### Supplier Emitting a Stream

~~~java
@Bean
Supplier<Flux<String>> pendingIds() {
    return () -> Flux.just("O-100", "O-101");
}
~~~

Each call to `get()` creates a new cold `Flux`. If the adapter calls the supplier again or re-subscribes, those IDs can be emitted repeatedly. This is an illustrative sample; real event sources need an appropriate read/mark-as-processed mechanism.

For a continuous source:

~~~java
@Bean
Supplier<Flux<Long>> ticks() {
    return () -> Flux.interval(java.time.Duration.ofSeconds(1));
}
~~~

`Flux.interval` is a time-driven stream and must be canceled when processing stops. Automatic supplier triggering, invocation schedules, and broker/serverless integration vary by adapter; do not treat a supplier bean as a standalone scheduler or delivery guarantee.

### Consumer and Asynchronous Tasks

`Consumer<Flux<T>>` returns `void`, so this signature does not directly express whether asynchronous processing completed or failed. With a reactive consumer, you must know whether the adapter manages the subscription or the consumer is responsible for it; calling `subscribe()` manually without managing errors, cancellation, and lifecycle makes tasks difficult to observe.

When the output needs to indicate that data writes have completed, you can choose a function returning `Mono<Void>`. Suppose `reactiveStore.save(order)` returns `Mono<?>`:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persistOrders = orders ->
    orders
        .concatMap(order -> reactiveStore.save(order))
        .then();
~~~

`then()` discards the successful write values and only emits a completion or error signal. This is a useful pattern if the adapter/caller supports awaiting the publisher's outcome. Do not confuse a constructed `Mono<Void>` with an already executed operation: the publisher still needs to be subscribed to.

## 6. Common Operators in Reactive Functions

| Operator | When to use | Common pitfalls |
| --- | --- | --- |
| `map` | Transform each element inline within the pipeline | Using it for blocking I/O calls or returning a nested `Mono` |
| `flatMap` | Call an asynchronous operation returning a publisher | Can reorder results when tasks finish at different times |
| `concatMap` | Run sequentially and preserve order | Lower peak throughput when operations are slow |
| `flatMapSequential` | Allow concurrent execution while emitting in source order | May have to buffer results waiting on earlier elements |
| `filter` | Drop elements that do not match a condition | Stream no longer has a 1–1 input/output relationship |
| `onErrorResume` | Turn an error into a fallback publisher | Placing it at the outermost level can terminate the rest of the stream |
| `timeout` | Limit wait time | Must define the policy when the timeout expires |
| `doOnNext` / `doOnError` | Attach metrics, logging, tracing | Not a substitute for business operations with asynchronous results |

### 6.1. `map` vs. `flatMap`

Suppose `fraudService.check(order)` returns `Mono<Decision>`:

~~~java
// Not what you want if you expect Flux<Decision>:
Flux<Mono<Decision>> nested = orders.map(fraudService::check);

// Flat output contract, capped at 8 concurrent tasks:
Flux<Decision> checked = orders.flatMap(
    fraudService::check,
    8
);
~~~

`flatMap` does not guarantee output order. If orders must be processed strictly in order, use `concatMap(fraudService::check)`; if you want concurrency while emitting results in original order, consider `flatMapSequential`.

### 6.2. Do Not Block the Processing Thread

The following practices can stall the event loop or processing threads:

~~~java
// Avoid in reactive logic performing I/O:
return orders.map(order -> blockingJdbcRepository.find(order.orderId()));
// Avoid: mono.block(), Thread.sleep(...), CompletableFuture.get()...
~~~

Prefer reactive clients/repositories that return `Mono` or `Flux` and compose them with `flatMap`. If you temporarily must integrate a blocking API, you can isolate it on a scheduler meant for blocking work:

~~~java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyClient.loadCustomer(customerId)
    )
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

This moves the blocking operation off the event loop; **it does not turn a blocking API into a non-blocking one**. You still must bound concurrency and evaluate timeouts, system load, connections, and cancellation behavior.

## 7. Per-Element vs. Stream-Wide Error Handling

In Reactive Streams, `onError` is a **terminal** signal for the subscription. An error in `map`, `flatMap`, or I/O can halt the entire stream if not handled at the right scope.

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> inspect =
    orders -> orders.flatMap(
        order -> fraudService.check(order)
            .timeout(java.time.Duration.ofSeconds(2))
            .onErrorResume(error -> Mono.just(
                new Decision(order.orderId(), false)
            )),
        8
    );
~~~

Here each inner task handles its own error, so a failure checking one order does not necessarily terminate processing for other orders. **Marking `false` is only correct if business policy allows safe rejection when the service fails.** If errors must be reported to the caller, let them propagate as `onError` or convert them into a business result that clearly represents an indeterminate state.

Conversely:

~~~java
orders.flatMap(fraudService::check)
    .onErrorResume(error -> Flux.empty());
~~~

The outermost `onErrorResume` replaces the failed stream with an empty publisher; it does not “skip the error and keep receiving future elements” from the terminated subscription. Do not use `onErrorContinue` as a default solution, because operator support varies and it easily corrupts state.

You can classify errors with `onErrorResume(SpecificException.class, ...)` and add `retryWhen` for transient failures, but only retry when the operation is idempotent or has deduplication mechanisms.

## 8. Working with Message and Metadata

When a function needs a correlation ID, partition key, or routing header, use Spring Messaging's `Message<T>` instead of extracting only the payload. Example transforming a string payload and copying appropriate headers:

~~~java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

Function<Flux<Message<String>>, Flux<Message<String>>> labelMessages =
    messages -> messages.map(message ->
        MessageBuilder
            .withPayload("checked:" + message.getPayload())
            .copyHeaders(message.getHeaders())
            .build()
    );
~~~

System-managed headers such as ID and timestamp may be regenerated; copying headers also does not override binder-specific rules. When input/output correlation must be preserved, explicitly identify required business headers (such as `correlationId`) and verify them through a real adapter.

Using `Flux<OrderEvent>` instead of `Flux<Message<OrderEvent>>` keeps business logic simpler, but envelope information may no longer be available inside the function. This is a trade-off between payload-only functions and metadata-aware functions.

## 9. FunctionCatalog, HTTP, Events, and Serverless

A `@Bean Function<Flux<OrderEvent>, Flux<Decision>>` remains plain Java logic. `FunctionCatalog` looks up functions by name, handles type metadata, performs matching conversions, and executes composition; the adapter decides how the function is invoked in a specific environment.

~~~mermaid
flowchart LR
    HTTP[HTTP request] --> Adapter[Spring Cloud Function adapter]
    Event[Event source / broker] --> Adapter
    Serverless[Serverless trigger] --> Adapter
    Adapter --> Catalog[FunctionCatalog]
    Catalog --> Fn[Reactive Function]
    Fn --> Pub[Result Mono / Flux]
    Pub --> Adapter
~~~

Key distinctions:

- **Over HTTP:** A request can be converted by the adapter into an input publisher, and the result publisher converted into an HTTP response. Returning results at once, streaming, JSON formatting, or SSE depends on the adapter, headers, and web configuration in use. Do not assume `Flux` will always be pushed element-by-element to the client immediately.
- **Over a broker/events:** The binder decides how to subscribe, send output messages, and manage acknowledgments/retries. A `Function<Flux<T>, Flux<R>>` can process a continuous stream and emit a different number of results than input messages. Check how the binder in use handles error bindings, backpressure, partitions, and metadata.
- **Over serverless:** The runtime may trigger the function per invocation and enforce execution time limits. An infinite stream is not suitable for every serverless model; determine invocation limits, how results are awaited, and timeout behavior.

When a module has multiple beans, configure `spring.cloud.function.definition` so the adapter knows which function is exported/bound. This is also where you select a composition chain such as `functionA|functionB`. Do not confuse `definition` with creating a new business bean.

### 9.1. Special Considerations for Reactive Functions

With a reactive function accepting `Flux`, “one function invocation” and “one element passing through the function” are two different things. The lambda may be invoked only once to construct a long-lived publisher pipeline; the `map`/`flatMap` operations inside run per element. Therefore:

- Do not initialize per-order business state outside the `map`/`flatMap` operators.
- Do not use mutable bean-level fields to hold data belonging to a single message, unless synchronization and scoping are explicitly designed.
- Do not assume transactions, retries, or acknowledgments automatically occur once per element just because the function has a `Flux` type.

## 10. Testing Reactive Behavior

`StepVerifier` from `reactor-test` lets you verify signals, ordering, completion, and errors without manually calling `subscribe()` in tests. Using the `OrderFunctions` configuration above:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OrderFunctionsTest {

    private final OrderFunctions functions = new OrderFunctions();

    @Test
    void checksEachOrder() {
        Flux<OrderFunctions.OrderEvent> input = Flux.just(
            new OrderFunctions.OrderEvent("O-100", 120),
            new OrderFunctions.OrderEvent("O-101", 0)
        );

        StepVerifier.create(functions.checkOrders().apply(input))
            .expectNext(
                new OrderFunctions.Decision("O-100", true),
                new OrderFunctions.Decision("O-101", false)
            )
            .verifyComplete();
    }

    @Test
    void sumsFiniteStream() {
        Flux<OrderFunctions.OrderEvent> input = Flux.just(
            new OrderFunctions.OrderEvent("O-100", 120),
            new OrderFunctions.OrderEvent("O-101", 0)
        );

        StepVerifier.create(functions.sumAmounts().apply(input))
            .expectNext(120L)
            .verifyComplete();
    }
}
~~~

For functions performing I/O, also test `Mono.empty()`, `Flux.empty()`, errors, timeouts, cancellation, and ordering under concurrent execution. A plain bean test verifies Reactor logic; to confirm payload conversion, definition selection, HTTP formatting, or message delivery, add integration tests through the actual adapter/binder.

## 11. Common Design Pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Function returns `Flux` but produces no output | No subscription; or waiting for stream completion | Check the subscriber and whether aggregating operators like `reduce`/`collectList` are used on an infinite stream |
| Function returns `Flux<Mono<R>>` | Using `map` with a call that returns `Mono<R>` | Use `flatMap`/`concatMap` as appropriate |
| Slow processing, stalls under higher load | Using JDBC, `block()`, or blocking APIs inside the pipeline | Replace with reactive APIs, or isolate blocking calls on `boundedElastic` |
| Out-of-order results | `flatMap` completes out of input order | Consider `concatMap` or `flatMapSequential` |
| A single error stops everything | `onError` terminates the subscription | Scope error handling per inner task or accept termination per business rules |
| Source data is re-sent | Cold publisher subscribed multiple times or supplier re-invoked | Design idempotency, source state, and replay policies |
| Memory grows on long-running streams | `collectList`, unbounded buffers, or excessive concurrency | Aggregate by windows, bound concurrency/capacity |
| Correlation ID is lost | Transforming payload only and dropping the envelope | Use `Message<T>` and preserve required business headers |
| HTTP response does not stream as expected | Streaming support depends on adapter and content negotiation | Check adapter, media types, and integration tests |
| `Consumer` task errors are hard to track | Internal subscription detached from caller | Manage the subscription or return a completion publisher when appropriate |

## 12. Self-Check Questions

1. Why might `Function<Flux<Order>, Mono<Long>>` emit no result if the event source runs infinitely?
2. When calling an API that returns `Mono<Decision>` for each `Order`, why do `map` and `flatMap` produce two different output types?
3. How does an error inside `flatMap` affect the overall subscription? Where should `onErrorResume` be placed if errors must be handled independently per order?
4. Who is responsible for subscribing to and canceling the publisher when a function is invoked via a Spring Cloud Function adapter? What can happen if the bean calls `subscribe()` itself?
5. What additional tests are needed before using the same reactive function across both HTTP and an event binder?

**Key takeaway:** `Mono` represents 0–1 elements and `Flux` represents 0–N elements; both are publishers with completion/error signals. In Spring Cloud Function, reactive signatures define the data processing contract, while `FunctionCatalog` and adapters determine how that logic is integrated into a specific invocation protocol. Writing pipelines that return publishers, clarifying subscription boundaries, scoping error handling properly, and testing adapter behavior are the core steps to reusing the same function reliably.
