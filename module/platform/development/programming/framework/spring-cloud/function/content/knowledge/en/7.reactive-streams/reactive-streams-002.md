# Distinguishing Per-Element Function Invocation from Once-Per-Stream Invocation

## 1. The Problem: Same Order Processing, Two Different Invocation Models

In Spring Cloud Function, business logic can be packaged as a `Supplier`, `Function`, or `Consumer` and looked up via `FunctionCatalog`. The same logic can be exposed by adapters over HTTP, events, or serverless environments. When using Project Reactor, a common source of confusion is:

> **How many times the function is invoked** is different from **how many elements are processed inside the publisher the function returns**.

Suppose a source emits three order events: `A`, `B`, and `C`. We need to inspect each order and return a corresponding result.

- With `Function<Order, Decision>`, the caller supplies **one `Order` per `apply(order)` call**. If an adapter uses a per-message model, three orders correspond to three function applications.
- With `Function<Flux<Order>, Flux<Decision>>`, the caller can supply **a single `Flux<Order>` containing all three orders** in one `apply(flux)` call. The outer lambda runs once to build the pipeline; the inner `map` operator then processes `A`, `B`, and `C` in turn once the stream is subscribed to.

Both designs can yield three results, yet their starting points, lifecycles, state handling, error behavior, and ability to aggregate across the stream differ.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **`Function.apply` invocations**, **`subscribe` subscriptions**, and **`onNext` element emissions**.
2. Identify when logic executes per element and when logic is attached to the entire stream.
3. Choose the appropriate signature among `Function<T,R>`, `Function<Mono<T>, Mono<R>>`, and `Function<Flux<T>, Flux<R>>`.
4. Explain how this choice affects state, error handling, message metadata, composition, and adapters.
5. Use `StepVerifier` to verify the number of invocations versus the number of elements actually processed.

## 2. Three Milestones That Must Not Be Conflated

For a reactive function, you should ask three distinct questions:

| Milestone | What happens? | When does it typically occur? |
| --- | --- | --- |
| **Function invocation** | The caller executes `function.apply(input)`; code directly in the lambda body runs to construct the result | When the adapter or application code invokes the function |
| **Stream subscription** | A subscriber subscribes to the returned publisher; the pipeline is activated according to Reactor semantics | When the framework/adapter or test consumes the result |
| **Element arrival** | The pipeline receives an `onNext(item)` signal and runs operators such as `map`, `filter`, or `flatMap` | Whenever a matching element arrives from the source |

In most *cold* Reactor pipelines, creating the publisher **does not yet** execute per-element transformations. However, Java code written **outside** the operators still runs immediately when `apply` is called.

~~~java
Function<Flux<String>, Flux<String>> normalize = source -> {
    System.out.println("apply: building pipeline");

    return source.map(value -> {
        System.out.println("map: processing " + value);
        return value.trim().toUpperCase();
    });
};

Flux<String> output = normalize.apply(Flux.just(" a ", " b "));
// Printed here so far: apply: building pipeline

// Once subscribed:
// map: processing  a
// map: processing  b
~~~

If a cold publisher is subscribed to again, the operations inside `map` may run again, **without necessarily** causing `apply` to run again. Conversely, if the caller calls `apply` multiple times, the function body can run multiple times even before anyone subscribes to the result.

The diagram below separates the two ways of applying a function:

~~~mermaid
flowchart TB
    subgraph I["Per element: Function<Order, Decision>"]
        IA["A"] --> IFA["apply(A)"]
        IB["B"] --> IFB["apply(B)"]
        IC["C"] --> IFC["apply(C)"]
        IFA --> IDA["Decision A"]
        IFB --> IDB["Decision B"]
        IFC --> IDC["Decision C"]
    end

    subgraph R["Per stream: Function<Flux<Order>, Flux<Decision>>"]
        RS["Flux containing A, B, C"] --> RF["apply(flux) once"]
        RF --> RP["Pipeline: map(decide)"]
        RP --> RX["Subscription and onNext signals"]
        RX --> RD["Decision A, B, C"]
    end
~~~

**“Called once for the entire stream” is only true within the scope of one caller passing one publisher into the function.** It is not a promise that the lambda is invoked only once over the entire application lifetime. HTTP may invoke it per request, an event binder may establish a long-lived pipeline, and each instance or restart can create additional invocations.

## 3. Approach 1: Function Accepting One Element at a Time

An imperative function typically looks like this:

~~~java
import java.util.function.Function;

Function<String, String> cleanOne =
    value -> value.trim().toUpperCase();
~~~

If the caller executes:

~~~java
String a = cleanOne.apply(" a ");
String b = cleanOne.apply(" b ");
String c = cleanOne.apply(" c ");
~~~

then the lambda body runs three times. Each call receives an independent value and returns a value directly.

In event-driven applications, an adapter supporting a message-by-message model can use a function of the form `Function<OrderEvent, Decision>` to process each message. The framework handles receiving the message, converting the payload, and calling the function with the concrete value; the function itself does not need to know about the broker or protocol.

### 3.1. “Per-Element Invocation” Can Still Live Inside a Reactor Pipeline

You can also use the very same imperative function inside `Flux.map`:

~~~java
Function<String, String> cleanOne =
    value -> value.trim().toUpperCase();

Flux<String> cleaned = Flux.just(" a ", " b ", " c ")
    .map(cleanOne::apply);
~~~

In this example, `cleaned` is constructed only once, yet `cleanOne.apply(...)` is called **every time `map` receives an element** in each subscription. What matters is where the call sits: it is **inside** the `map` operator's callback.

Therefore, do not judge “per-element invocation” merely by whether a code snippet uses `Flux`. Identify precisely **what object is passed to `apply`** and **where `apply` is executed**.

### 3.2. Characteristics of Imperative Functions

- Easy to write and test for pure one-in/one-out logic.
- Each `apply` call has its own argument and result.
- Well suited for per-message processing that does not need state from other messages.
- If blocking I/O is placed inside the lambda, calling this function inside a reactive pipeline **does not** automatically make the I/O asynchronous.
- Per-message retries, transactions, and acknowledgments are designed by the caller/adapter; the `Function<T,R>` type alone provides no such guarantees.

## 4. Approach 2: Function Accepting One Publisher Representing the Stream

A reactive function typically looks like this:

~~~java
Function<Flux<String>, Flux<String>> cleanStream =
    input -> input.map(value -> value.trim().toUpperCase());
~~~

The caller can apply the function to a `Flux`:

~~~java
Flux<String> source = Flux.just(" a ", " b ", " c ");
Flux<String> result = cleanStream.apply(source);
~~~

Here:

1. `cleanStream.apply(source)` runs once and returns a new `Flux<String>`.
2. `result` represents the pipeline; with the cold source above, `map` has not run yet.
3. When `result` gets a subscriber, `map` runs for each emitted element.
4. When the source emits `onComplete`, the output also completes if there are no errors and operators do not alter termination behavior.

**One function invocation does not mean only one element is processed.** The pipeline can process 0, 1, millions of elements, or keep running until canceled.

### 4.1. Mono Has the Same Boundary

~~~java
Function<Mono<String>, Mono<String>> cleanMono =
    input -> input.map(String::trim);
~~~

`cleanMono.apply(mono)` creates the result publisher; the `map` callback only runs if the input actually emits a value during the subscription. With `Mono.empty()`, no element passes through `map`. A cold `Mono` can be subscribed to multiple times, so “at most one value” applies to **a single subscription**, not a guarantee that the task runs only once forever.

### 4.2. Limits on What “Once” Means

A function of type `Function<Flux<T>, Flux<R>>` accepts the stream as a whole at the API level, yet **that does not mean it loads all elements into memory at once**. Operators normally process signals incrementally according to downstream demand (backpressure). Only accumulating operators such as `collectList()`, `reduce()`, or certain forms of buffering need to wait for part or all of the data by their contract.

## 5. Spring Cloud Function Example: Two Beans for the Same Business Rule

Let's implement two ways of checking orders. The business rule is that an order with `amountCents > 0` is accepted. The example uses Java 17+ (for `record`), Spring Framework/Spring Cloud Function, and Project Reactor.

~~~java
package demo;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class OrderFunctionConfig {

    public record OrderEvent(String id, long amountCents) { }
    public record Decision(String id, boolean accepted) { }

    private static Decision decide(OrderEvent order) {
        return new Decision(order.id(), order.amountCents() > 0);
    }

    // Calls apply(...) with one order at a time.
    @Bean
    public Function<OrderEvent, Decision> decideOne() {
        return OrderFunctionConfig::decide;
    }

    // Calls apply(...) with a Flux; map processes each order on onNext.
    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> decideStream() {
        return source -> source.map(OrderFunctionConfig::decide);
    }
}
~~~

Both rely on **one** pure `decide` method, so the business rule is not duplicated. However, they have different invocation contracts:

| Aspect | `decideOne` | `decideStream` |
| --- | --- | --- |
| Input type | `OrderEvent` | `Flux<OrderEvent>` |
| Output type | `Decision` | `Flux<Decision>` |
| Caller invokes `apply` | Every time an order needs processing | Every time a `Flux` source is supplied |
| Processing each order | Inside the body of `decide` itself | Inside the `map` callback as the stream emits data |
| Outcome if source has three orders | Three calls returning three `Decision` values | One call returning one `Flux` that emits three `Decision` values |
| Aggregating multiple orders in one call | Requires gathering data externally | Can use `window`, `buffer`, `reduce`, etc. as needed |
| Signal lifecycle | Direct return value or Java exception | `onNext`, `onComplete`, or `onError` emitted by the publisher |

In an application with multiple function beans, an adapter usually needs to know which function to expose/bind. For example, selecting one of the two:

~~~properties
spring.cloud.function.definition=decideStream
~~~

`FunctionCatalog` handles looking up and composing function beans by name, and integrates type conversion with adapters. It **does not** erase the difference between applying one `OrderEvent` and applying one `Flux<OrderEvent>`.

### 5.1. Plain Java Invocation Illustration

~~~java
OrderFunctionConfig configuration = new OrderFunctionConfig();

var one = configuration.decideOne();
var many = configuration.decideStream();

OrderFunctionConfig.OrderEvent a =
    new OrderFunctionConfig.OrderEvent("A", 100);
OrderFunctionConfig.OrderEvent b =
    new OrderFunctionConfig.OrderEvent("B", 0);

// Two imperative function calls:
OrderFunctionConfig.Decision resultA = one.apply(a);
OrderFunctionConfig.Decision resultB = one.apply(b);

// One reactive function call to build a pipeline for two orders:
Flux<OrderFunctionConfig.Decision> results =
    many.apply(Flux.just(a, b));
~~~

`resultA` and `resultB` are complete values as soon as `apply` returns. By contrast, `results` is a publisher; for elements to flow through `map`, a subscription is required. When running inside Spring Cloud Function, subscribing is typically the caller's/adapter's responsibility.

## 6. Experiment Counting Exact apply, subscribe, and onNext Events

Here is a way to inspect the difference without depending on HTTP or a message broker. Three counters are placed in three different spots:

~~~java
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger applyCalls = new AtomicInteger();
AtomicInteger subscriptions = new AtomicInteger();
AtomicInteger processedItems = new AtomicInteger();

Function<Flux<String>, Flux<String>> uppercaseStream = input -> {
    applyCalls.incrementAndGet();

    return input
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .map(item -> {
            processedItems.incrementAndGet();
            return item.toUpperCase(Locale.ROOT);
        });
};

Flux<String> output = uppercaseStream.apply(
    Flux.just("a", "b", "c")
);

// Right after apply:  applyCalls=1; subscriptions=0; processedItems=0

StepVerifier.create(output)
    .expectNext("A", "B", "C")
    .verifyComplete();

// After the first subscription:
// applyCalls=1; subscriptions=1; processedItems=3

StepVerifier.create(output)
    .expectNext("A", "B", "C")
    .verifyComplete();

// After the second subscription on the same cold publisher:
// applyCalls=1; subscriptions=2; processedItems=6
~~~

| Point in time | `applyCalls` | `subscriptions` | `processedItems` |
| --- | ---: | ---: | ---: |
| Before `apply` | 0 | 0 | 0 |
| After `apply`, before `StepVerifier` | 1 | 0 | 0 |
| After first `verifyComplete()` | 1 | 1 | 3 |
| After second `verifyComplete()` | 1 | 2 | 6 |

This behavior holds for the pipeline and *cold* `Flux.just(...)` source in the example. A hot source, a subscription-sharing source, or an external source will replay differently. Counting subscriptions at one point in the pipeline also does not necessarily equal the total number of network connections or broker message deliveries.

### 6.1. What Happens If apply Is Called Twice?

~~~java
Flux<String> first = uppercaseStream.apply(Flux.just("a"));
Flux<String> second = uppercaseStream.apply(Flux.just("b"));
// applyCalls increased by 2, even though neither first nor second has been subscribed to yet.
~~~

The pipeline-constructing function is called as many times as the caller applies it. Never assume “Spring only calls this once” in shared business logic, especially when the same function is exposed across multiple adapters.

### 6.2. What Happens When Processing Elements with a Separate Function?

~~~java
AtomicInteger oneCalls = new AtomicInteger();

Function<String, String> uppercaseOne = text -> {
    oneCalls.incrementAndGet();
    return text.toUpperCase(Locale.ROOT);
};

Flux<String> output = Flux.just("a", "b", "c")
    .map(uppercaseOne::apply);
~~~

Each subscription to `output` calls `uppercaseOne.apply` three times with this cold source. Even though the entire snippet uses Reactor, **the `uppercaseOne.apply` call still happens per element**. This is the crucial distinction between a *function taking a Flux* and a *function taking T called from a Flux*.

## 7. Why Spring Cloud Function and Adapters Behave Differently

Spring Cloud Function decouples `Supplier`, `Function`, and `Consumer` logic from the triggering mechanism. Consequently, the same bean can be invoked at different cadences depending on the adapter and runtime environment.

### 7.1. Direct Invocation via FunctionCatalog

A caller can look up a function by name and explicitly feed values into it:

~~~java
// Illustrating the invocation contract, omitting bean/catalog lookup:
Decision decision = decideOne.apply(order);
Flux<Decision> stream = decideStream.apply(orderFlux);
~~~

The caller decides how many times to call `apply`, how many elements `orderFlux` contains, and who subscribes to `stream`. `FunctionCatalog` handles function types and wrappers, but it does not guarantee that every function is invoked on the same cadence.

### 7.2. Over HTTP

An HTTP adapter typically structures invocations per HTTP request. A new request can result in a new function application. If the input is mapped to a `Flux<T>`, the reactive function receives a publisher scoped to that invocation; exact request formatting, buffering/streaming, and response type depend on the adapter, version, configuration, and content negotiation.

Do not infer that:

- Every `Flux` automatically equals “all HTTP traffic since server startup.”
- Every HTTP request with a JSON array automatically becomes a `Flux` handled identically.
- Returning a `Flux` always means the client immediately receives each element over a streaming connection.

To confirm behavior, write integration tests over HTTP with the actual media types and runtime.

### 7.3. Over Events or Spring Cloud Stream

In a single-message processing model, an imperative function `Function<Event, Result>` is typically called for **each message**. The binder receives each message, optionally converts the payload, invokes the function, and forwards the result to the next channel/broker.

With a reactive function `Function<Flux<Event>, Flux<Result>>`, a stream-capable binder can establish **a single pipeline** and feed data into it over time. The outer function lambda is usually applied when wiring the pipeline; subsequent elements flow through the inner operators. Some binders or configurations may recreate the pipeline on restarts, re-binding, or re-subscription.

~~~mermaid
flowchart LR
    E1["Event A"] --> BUS["Event binder"]
    E2["Event B"] --> BUS
    E3["Event C"] --> BUS
    BUS --> FX["Flux<Event>"]
    FX --> FN["Function.apply(flux)"]
    FN --> PIPE["map / flatMap / filter"]
    PIPE --> OUT["Flux<Result>"]
    OUT --> OB["Output binding"]
~~~

The number of times the message-handling callback runs **is not equal** to the number of times the outermost function lambda is called. Furthermore, Reactor backpressure signals do not automatically guarantee that the broker pauses or that acknowledgments happen per element. Those depend on the binder, connector, offset/ack mode, and configuration.

### 7.4. Over Serverless

Serverless runtimes typically enforce per-invocation boundaries, timeouts, and resource limits. A reactive function may construct a publisher per invocation; the framework must await or stream results according to the supported protocol. An infinite stream does not naturally fit a short-lived invocation model. If continuous event processing is required, check how the adapter maintains the source, when it terminates, and its retry/ack policies.

## 8. Scenarios That Require “Whole-Stream” Processing

The `Function<Flux<T>, Flux<R>>` signature is not merely a syntactic variant of `Function<T,R>`. It allows a single function application to build a pipeline containing operations that need to know **relationships across multiple elements**.

### 8.1. Filtering, Transforming, and Windowing/Batching

~~~java
Function<Flux<Long>, Flux<Long>> rollingTotals = amounts ->
    amounts
        .filter(amount -> amount > 0)
        .buffer(3)
        .map(batch -> batch.stream()
            .mapToLong(Long::longValue)
            .sum());
~~~

With a finite source emitting `10, -1, 20, 30, 40`, after filtering we get `10, 20, 30, 40`; `buffer(3)` creates two batches, so the resulting publisher emits `60` and `40`. A partial batch of fewer than three elements is also emitted when the source completes normally.

This logic is awkward to express with a pure one-in/one-out `Function<Long, Long>` because each output depends on multiple elements. When the source runs indefinitely, a trailing batch with fewer than three elements may have to wait for future elements or stream termination.

### 8.2. End-of-Stream Aggregation: Flux In, Mono Out

~~~java
Function<Flux<Long>, Mono<Long>> totalAfterComplete =
    values -> values.reduce(0L, Long::sum);
~~~

The caller applies the function only **once** to a `Flux<Long>`; `reduce` processes elements sequentially but waits for `onComplete` before emitting the sum. If the event stream runs forever and never completes, there is no “final total” to return.

When you need periodic total updates from an unbounded stream, use time/count windows, or a stateful accumulation that emits multiple intermediate results (such as `scan`) according to the business contract.

### 8.3. Calling Asynchronous I/O Per Element

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> checkAsync =
    orders -> orders.flatMap(
        order -> fraudService.check(order), // Mono<Decision>
        8 // at most 8 concurrent inner tasks
    );
~~~

`checkAsync.apply(orders)` still constructs the pipeline only once for the passed-in publisher. However, `fraudService.check(order)` can be invoked **every time an element arrives**, with up to 8 concurrent inner publishers active in this example. `flatMap` can emit results out of input order; use `concatMap` or `flatMapSequential` when ordering outweighs concurrent throughput.

*The `checkAsync` snippet only illustrates the structure: `OrderEvent`, `Decision`, and `fraudService.check` are hypothetical application types/services.*

## 9. Impact on State and Resources

### 9.1. Variables Outside Operators Are Only Initialized on apply

~~~java
Function<Flux<Integer>, Flux<Integer>> numberItems = source -> {
    AtomicInteger counter = new AtomicInteger();

    return source.map(value -> counter.incrementAndGet());
};
~~~

Within a single `apply`, `counter` is created once and shared across the elements passing through that pipeline. If the **same** resulting publisher is subscribed to again, the counter is still the same object, so values can continue increasing. If the caller calls `apply` again to create a new publisher, a new counter is created. This is a frequent source of bugs when developers mistake a variable inside the function for a “per-message variable.”

In environments with multiple subscriptions or parallel execution, shared state also requires concurrency care. Pure transformations or stateful operators such as `scan`/`window` are easier to reason about.

### 9.2. Need Separate State Per Subscription?

You can defer state creation until subscription time using `Flux.defer`:

~~~java
Function<Flux<String>, Flux<String>> numberPerSubscription =
    source -> Flux.defer(() -> {
        AtomicInteger sequence = new AtomicInteger();

        return source.map(value ->
            sequence.incrementAndGet() + ":" + value
        );
    });
~~~

With a finite cold source, each subscription to the result creates a fresh `sequence` starting at 0. `defer` **does not** change how many times `apply` is called; it changes when the publisher and state inside the `defer` callback are created. When using hot streams or sources that can share subscriptions, you still need to consider the specific source lifecycle.

### 9.3. Side Effects, Retries, and Duplicates

If a lambda running inside `map` writes to a database or calls an external API, it can run again when a cold publisher is subscribed to another time or when a retry mechanism re-subscribes. Therefore:

- Do not assume a single `apply` call implies side effects execute strictly once.
- For events that may be replayed, design idempotency keyed by event/order ID.
- Do not call `subscribe()` yourself inside a `Function<Flux<T>, Flux<R>>` bean when the adapter owns the publisher; doing so easily detaches errors and cancellation from the caller.
- When an operation returns `Mono<?>`, compose it with `flatMap`/`concatMap` instead of `map`, which would produce `Flux<Mono<?>>` with nothing subscribing to the inner tasks.

## 10. Impact on Errors, Ordering, and Message Boundaries

| Scenario | Function accepting single `T` | Function accepting `Flux<T>` |
| --- | --- | --- |
| An element encounters an error | Current invocation can throw an exception | An unhandled error produces `onError` and usually terminates the active subscription |
| Need to drop only the failed element | Caller/adapter decides whether to continue with other messages | Handle inside each element's inner publisher, depending on business rules |
| Preserving order | May depend on the order the caller invokes and processes | `map` preserves order; `flatMap` can reorder; `concatMap` processes sequentially |
| Need headers/message keys | Caller can pass `Message<T>` into the function | Can use `Flux<Message<T>>` to retain the envelope per element |
| Transaction/ack | Not automatically guaranteed by the signature | Not automatically guaranteed by subscription or `onComplete` |

Example of scoping a service error per order:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> safeCheck =
    orders -> orders.flatMap(
        order -> fraudService.check(order)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(new Decision(order.id(), false))
            ),
        8
    );
~~~

This illustrates a *fail closed* policy. Only turn an error into `false` if business rules genuinely accept treating a check failure as rejecting the order; if you need to distinguish error states, use a result type with an explicit status.

Conversely, an `onErrorResume` placed **after** the entire `flatMap` only replaces the already-failed stream and **does not** restart the old subscription from the next element. In long-lived message streams, choosing where to place error handling directly affects whether subsequent messages continue to be processed.

### 10.1. Per-Message Headers Do Not Automatically Become a Stream-Wide Header

If each event's correlation ID or routing key is needed, the signature can be:

~~~java
Function<Flux<Message<OrderEvent>>, Flux<Message<Decision>>> route =
    messages -> messages.map(message ->
        MessageBuilder
            .withPayload(decide(message.getPayload()))
            .copyHeaders(message.getHeaders())
            .build()
    );
~~~

You must import `org.springframework.messaging.Message` and `MessageBuilder`. Copying headers demonstrates intent, though some framework-managed headers may be regenerated or handled specially by binders. When aggregating N messages into a single result, explicitly specify which metadata is retained, aggregated, or dropped; you cannot arbitrarily take the first element's header as the header for the entire stream.

## 11. Composition: Which Function Processes Elements, Which Processes the Stream?

Spring Cloud Function supports lookup and composition via `FunctionCatalog`. For example:

~~~java
@Bean
Function<String, String> normalizeOne() {
    return String::trim;
}

@Bean
Function<String, String> labelOne() {
    return value -> "checked:" + value;
}
~~~

An adapter can select:

~~~properties
spring.cloud.function.definition=normalizeOne|labelOne
~~~

At the imperative business level, each invocation of the composition applies both steps to **one** value. If the adapter invokes the composition per message, the composed pipeline also runs per message.

In reactive form:

~~~java
@Bean
Function<Flux<String>, Flux<String>> normalizeStream() {
    return source -> source.map(String::trim);
}

@Bean
Function<Flux<String>, Flux<String>> labelStream() {
    return source -> source.map(value -> "checked:" + value);
}
~~~

and:

~~~properties
spring.cloud.function.definition=normalizeStream|labelStream
~~~

The composition builds a pipeline of two transformations, and each element passes sequentially through the two `map` operators. **Do not infer how many times the composition was applied merely by counting elements.**

Mixing imperative functions, reactive functions, `Mono`, `Flux`, and `Message` depends on the type adaptation capabilities of your Spring Cloud Function version and specific adapter. When requirements involve aggregation, one-to-many splitting, or message headers, verify the composition with integration tests rather than assuming a one-to-one mapping.

## 12. Supplier and Consumer Also Have Two Lifecycle Levels

Although this topic focuses on `Function`, distinguishing **functional API invocations** from **element processing** also applies to the other two interfaces.

| Role | Single-value signature | Publisher signature | Lifecycle questions |
| --- | --- | --- | --- |
| Supplier | `Supplier<T>` | `Supplier<Flux<T>>` | How many times does the adapter call `get()`? Who subscribes to the returned publisher? |
| Function | `Function<T,R>` | `Function<Flux<T>, Flux<R>>` | How many times does the caller call `apply()`? How many `onNext` signals flow through the operators? |
| Consumer | `Consumer<T>` | `Consumer<Flux<T>>` | Who receives and consumes the source? Who manages subscription, errors, and cancellation? |

Example:

~~~java
@Bean
Supplier<Flux<Long>> heartbeat() {
    return () -> Flux.interval(Duration.ofSeconds(1));
}
~~~

When `get()` returns a `Flux.interval`, elements are emitted over time once subscribed. You cannot count emitted elements by counting how many times the supplier's `get()` is called. Whether the adapter triggers the supplier automatically, calls `get()` repeatedly, or maintains a long-lived subscription must be verified in your target environment.

Especially with `Consumer<Flux<T>>` returning `void`, never assume the caller receives completion and error signals from asynchronous work. Understand the adapter's conventions and manage subscriptions appropriately; where the caller needs to observe completion, consider a function returning a publisher such as `Function<Flux<T>, Mono<Void>>` if the adapter supports that contract.

## 13. Testing So You Do Not Confuse the Two Invocation Models

The following test uses `StepVerifier` to confirm that the function body runs once while the operator processes three elements. It uses Reactor Test and JUnit 5.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class InvocationBoundaryTest {

    @Test
    void oneApplyCanProcessThreeItems() {
        AtomicInteger applications = new AtomicInteger();
        AtomicInteger items = new AtomicInteger();

        Function<Flux<Integer>, Flux<Integer>> doubleAll = source -> {
            applications.incrementAndGet();

            return source.map(value -> {
                items.incrementAndGet();
                return value * 2;
            });
        };

        Flux<Integer> result = doubleAll.apply(Flux.just(1, 2, 3));

        assertEquals(1, applications.get());
        assertEquals(0, items.get());

        StepVerifier.create(result)
            .expectNext(2, 4, 6)
            .verifyComplete();

        assertEquals(1, applications.get());
        assertEquals(3, items.get());
    }

    @Test
    void perItemFunctionIsAppliedThreeTimes() {
        AtomicInteger applications = new AtomicInteger();

        Function<Integer, Integer> doubleOne = value -> {
            applications.incrementAndGet();
            return value * 2;
        };

        Flux<Integer> result =
            Flux.just(1, 2, 3).map(doubleOne::apply);

        assertEquals(0, applications.get());

        StepVerifier.create(result)
            .expectNext(2, 4, 6)
            .verifyComplete();

        assertEquals(3, applications.get());
    }
}
~~~

Both tests expect `2, 4, 6`, yet where `apply` sits changes significantly: one test calls it once with a whole `Flux`, while the other calls it three times with three numbers.

For production code using adapters, add integration tests confirming:

- How many invocations are created for one HTTP request or for N messages.
- Business headers are preserved properly when the function accepts `Message<T>` or `Flux<Message<T>>`.
- Binder errors, retries, and acknowledgments operate at the intended boundaries.
- Streams are consumed and canceled on application shutdown, client disconnect, or serverless timeout.

## 14. Common Misconceptions

| Misconception | Accurate interpretation |
| --- | --- |
| “Accepting `Flux<T>` means the lambda runs N times for N elements.” | `apply(flux)` may run once; callbacks inside operators are what run per element. |
| “The function is only invoked once at application startup.” | That can happen when a binder builds a long-lived pipeline, but HTTP requests, restarts, multiple instances, or other callers can trigger new invocations. |
| “`apply` returned a `Flux`, so the data has been processed.” | Publishers are usually lazy; a subscription is needed for the pipeline to run. |
| “One `apply` call means side effects run exactly once.” | Resubscription/retries on cold publishers can re-run inner operations. |
| “Passing `Function<T,R>` to `map` invokes it once for the whole `Flux`.” | The `map` callback invokes the function for each `T` in each subscription. |
| “`Flux` always has enough data to compute a final total.” | Sources can be infinite; end-of-stream `reduce` must wait for `onComplete`. |
| “An error in one message only cancels that message.” | Unhandled `onError` is a subscription-terminating signal; you must choose the error-handling scope. |
| “Reactive means non-blocking.” | Calling JDBC, `Thread.sleep`, or `block()` inside operators can still block threads. |
| “A single stream equals a single transaction or acknowledgment.” | Transactions and message acknowledgments follow the I/O system and adapter, not the `Flux` signature alone. |

## 15. Signature Selection Rules and Self-Assessment Questions

Choose `Function<T,R>` when the business logic naturally processes each input independently, the adapter operates message-by-message, and stream-level access to the data flow is unnecessary. Choose `Function<Flux<T>, Flux<R>>` when the caller can supply a publisher, or when you need transformations, concurrency control, windowing, state, or aggregations tied to the stream. Choose `Function<Mono<T>, Mono<R>>` when a single invocation's input/output contract is at most one asynchronous value. Every choice should be verified against your concrete adapter for lifecycle, errors, backpressure, and metadata.

Assess yourself with the following scenarios:

1. `Function<Flux<Order>, Flux<Decision>>` is called via `apply` once with 100 orders. If it uses plain `map` and is subscribed to once, how many times does the code inside the `map` callback run?
2. When the same cold publisher is subscribed to twice without calling `apply` again, do counters outside and inside `map` change identically?
3. In an application receiving continuous messages, why might `Function<Flux<Order>, Mono<Total>>` emit no value at all?
4. Does passing a `Function<Order, Decision>` into `Flux.map(function::apply)` mean the function is invoked for the whole stream or per element?
5. With three events, why is the number of outermost lambda invocations insufficient to infer how many times a fraud-check API inside `flatMap` was called?
6. Before exposing a reactive function over both HTTP and an event binder, what do you need to verify regarding invocation, subscription, buffering, errors, and message acknowledgment?

**Key takeaway:** `apply` is the Java call that applies a function to **one argument**—that argument can be a `T` or a `Flux<T>`. `subscribe` triggers consumption of the publisher. `onNext` causes per-element transformations to run. When writing Spring Cloud Function code, establish clearly **who calls the function, who subscribes, and at what cadence data flows** before deciding where to place logic, state, and error handling.
