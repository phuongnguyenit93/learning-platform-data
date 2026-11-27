# Splitting One Stream into Multiple Outputs

## 1. When do you need to split a data stream?

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), business logic is packaged into `Supplier`, `Function`, and `Consumer` beans. As a result, a function can be managed by `FunctionCatalog`, participate in composition, benefit from message conversion, and integrate with HTTP, event systems, or serverless environments through an appropriate adapter.

A common requirement in event-driven systems is **routing events entering the same stream to different outputs**. For example, all orders arrive on the `orders.received` topic, but:

- Orders of **1,000,000 VND or more** must go to `orders.priority` for priority processing.
- Orders **below 1,000,000 VND** go to `orders.standard`.

The function needs to receive **one input stream** and produce **two output streams** with separate destinations. This is a *scatter*, *split*, or *fan-out* problem depending on how events are distributed.

~~~text
                                      ┌─► orders.priority ─► Priority processing
orders.received ─► splitOrders ───────┤
                                      └─► orders.standard ─► Standard processing
                    1 input                   2 outputs
~~~

Here, **two outputs** means two independent ports/bindings. This differs from a single port emitting many items: `Flux<Order>` can emit millions of orders while still representing **one stream**.

After this lesson, you will be able to:

1. Distinguish between *exclusive partitioning* and *event broadcasting* when splitting a stream.
2. Declare a `Function<Flux<T>, Tuple2<Flux<A>, Flux<B>>>` bean.
3. Share a `Flux` source so branches do not accidentally subscribe to the source multiple times.
4. Map each output to a separate binding in Spring Cloud Stream.
5. Test both branches, including boundary data and upstream subscription count.

## 2. Two stream-splitting patterns to distinguish

The same function signature can serve two very different business requirements:

| Distribution type | How it works | Example |
| --- | --- | --- |
| **Partitioning** (*partition*) | Each event belongs to **one** branch according to a rule; branches do not overlap when conditions are mutually exclusive | High-value orders → priority; all others → standard |
| **Duplicating/broadcasting** (*broadcast/fan-out*) | The same event can go to **multiple** branches | One order → processing system and monitoring system |

Technically, both can share the signature `Function<Flux<Order>, Tuple2<Flux<...>, Flux<...>>>`. **The signature only specifies the number of outputs; the logic inside the branches determines which events appear where.**

When partitioning, clarify three cases:

- **Gaps:** Could any event fail to match any branch? Is that allowed?
- **Overlaps:** Could any event appear in both branches? If so, is that intentional or a bug?
- **Boundaries:** With the condition `total >= 1_000_000`, which group does an order with total exactly `1_000_000` belong to?

An easy-to-test design uses complementary conditions: `>=` and `<`. Then every valid numeric value is routed to exactly one branch.

## 3. Function signature representing two outputs

In Spring Cloud Function, the multi-port model relies on **reactive function arity**, where `Flux` represents streams and Project Reactor's `TupleN` represents the port count and each port's type:

~~~java
Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
~~~

Reading from the inside out:

- `Flux<Order>` on the left: **one** input stream of `Order` objects.
- `Tuple2<..., ...>` on the right: the result contains **two** elements.
- First element `getT1()`: output stream index **0**.
- Second element `getT2()`: output stream index **1**.

`Tuple2` is created using `Tuples.of(first, second)` in the `reactor.util.function` package. The two elements do not need to have the same type. For example, if two different payload types must be emitted, the contract can be:

~~~java
Function<Flux<Order>, Tuple2<Flux<PriorityOrder>, Flux<StandardOrder>>>
~~~

Spring Cloud Function uses the **count** and **type** of the tuple elements to identify ports for reactive functions; Spring Cloud Stream can map those ports to corresponding bindings. This multi-output function arity mechanism is designed for **reactive functions**.

**Do not confuse the following types:**

| Return type | Meaning |
| --- | --- |
| `Flux<Order>` | One output carrying multiple orders |
| `Flux<List<Order>>` | One output where each item is a list |
| `Flux<Tuple2<A, B>>` | One output where each item is a pair of values |
| `Tuple2<Flux<A>, Flux<B>>` | **Two outputs** that are two independent publishers |
| `Tuple2<A, B>` | Two Java values; by itself does **not** create two output bindings of a reactive function |

## 4. Complete example: partitioning orders into two streams

The following example uses **Java 17+** (for declaring a `record`). `Order` contains an order ID and total amount in VND, without Kafka or RabbitMQ connection logic. The routing rule is written inside a Spring bean:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class OrderRoutingConfig {

    public record Order(String id, long totalVnd) {
    }

    @Bean
    public Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
            splitOrders() {

        return input -> {
            // Both branches share the same subscription to input.
            // The source is only connected once both branches have subscribed.
            Flux<Order> shared = input.publish().autoConnect(2);

            Flux<Order> priority = shared
                    .filter(order -> order.totalVnd() >= 1_000_000L);

            Flux<Order> standard = shared
                    .filter(order -> order.totalVnd() < 1_000_000L);

            // The order here determines the output binding indices.
            return Tuples.of(priority, standard);
        };
    }
}
~~~

Sample data:

| Input order | Total amount | Emitted branch |
| --- | ---: | --- |
| `O-101` | 1,500,000 VND | `priority` → output 0 |
| `O-102` | 230,000 VND | `standard` → output 1 |
| `O-103` | 1,000,000 VND | `priority` → output 0 |
| `O-104` | 999,999 VND | `standard` → output 1 |

Key points to understand at each step:

1. `input` is the data source, which does not necessarily emit items immediately when `apply` is called.
2. `publish().autoConnect(2)` creates a **shared** stream and waits for **two subscribers** before subscribing to the source.
3. The two `filter` branches receive items from the same shared source; each branch emits only the items matching its condition.
4. `Tuples.of(priority, standard)` returns two streams in a fixed order. The framework/adapter determines how to subscribe to each stream and send items to the corresponding destination.

This example intentionally handles every `long` value using the comparison rule. In a real-world application, if negative totals or missing data are invalid, add validation and a dedicated handling policy, such as discarding with logging or adding an error branch per business requirements.

## 5. Mapping two streams to two output bindings

`FunctionCatalog` helps Spring Cloud Function discover and look up the `splitOrders` bean. When using **Spring Cloud Stream**, the `1 → 2` model above has the default binding names:

| Binding | Element in function | Example source/target |
| --- | --- | --- |
| `splitOrders-in-0` | `Flux<Order> input` | `orders.received` |
| `splitOrders-out-0` | `Tuple2.getT1()` – `priority` | `orders.priority` |
| `splitOrders-out-1` | `Tuple2.getT2()` – `standard` | `orders.standard` |

`application.yml` configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: splitOrders
    stream:
      bindings:
        splitOrders-in-0:
          destination: orders.received
          content-type: application/json
        splitOrders-out-0:
          destination: orders.priority
          content-type: application/json
        splitOrders-out-1:
          destination: orders.standard
          content-type: application/json
~~~

The configuration above assumes the application already has the appropriate dependencies, including Spring Cloud Function, Spring Cloud Stream, and a **binder** for the chosen messaging system. A `Function` bean does not create a broker by itself; `destination` configuration only takes effect when the adapter/binder is actually initialized.

**Do not reverse the tuple order when editing code.** If you change `return Tuples.of(priority, standard)` to `Tuples.of(standard, priority)` while keeping the YAML unchanged, data will be sent to the wrong destination even though the application may still start up. Clearly define the contract for each index and test against the binding configuration.

Each output binding can configure its own message conversion, producer, partitioning, or error-handling policies depending on the binder's capabilities. Because the two outputs can have **different payload types**, the generic type information inside `Tuple2` is valuable when the framework converts data.

## 6. Why splitting a Flux into two branches requires subscription management

This is the most critical part when implementing a split with reactive code.

### 6.1. A pattern that easily subscribes to the source twice

The snippet below creates two branches directly from `input`:

~~~java
Flux<Order> priority = input
        .filter(order -> order.totalVnd() >= 1_000_000L);
Flux<Order> standard = input
        .filter(order -> order.totalVnd() < 1_000_000L);

return Tuples.of(priority, standard);
~~~

With a **cold publisher**, subscribing to each branch can re-subscribe to `input`. This can cause:

- Re-running queries, HTTP requests, or source-generating tasks.
- Repeating side effects such as recording an event twice.
- Processing two different datasets if the source changes between subscriptions.

Two independent subscriptions are occasionally desirable. However, if the goal is **reading the source once and distributing to two branches**, you need a shared connection as in the `publish().autoConnect(2)` example.

### 6.2. Why does `publish().autoConnect(2)` fit the example?

~~~text
                subscribe branch A
                         │
                         ▼
               ┌───────────────────┐
input ─────────┤ publish()         ├──► priority.filter(...)
               │ autoConnect(2)    │
               └───────────────────┘
                         │
                         ▼
                subscribe branch B ──► standard.filter(...)

Once both subscribers are present → starts connecting to input.
~~~

- `publish()` creates a `ConnectableFlux` that shares data from the source.
- `autoConnect(2)` connects to the source after **two subscriptions** have registered.
- For subscribers present at the time of connection, both branches observe the same event stream; `filter` determines which branch emits each item.

**Required assumption of this pattern:** both outputs are subscribed to. If you only pull the priority branch with `getT1().collectList().block()`, the source **never connects** because the second subscriber is missing. Therefore, a test that runs each branch sequentially can hang indefinitely.

`autoConnect(2)` does not automatically disconnect when only one subscriber remains. If the application lifecycle requires reconnecting when the subscriber count drops, `refCount(2)` is another mechanism to evaluate. The choice depends on the adapter's subscription lifecycle.

### 6.3. Backpressure and a slow branch

`publish()` respects downstream subscriber *demand*. If one branch is slow or requests no more items, demand propagated to the shared source may be throttled; the other branch can be affected as well. This is a consequence of **sharing a single backpressured source**, not a bug in `filter`.

When two downstream systems consume events at very different speeds, clarify expectations around latency, buffering, broker-level routing, retries, and policies when one destination fails. Avoid hastily adding an unbounded `onBackpressureBuffer()` or `cache()` to an infinite stream, as they can cause uncontrolled memory growth.

### 6.4. Commonly confused options

| Approach | Behavior to watch out for |
| --- | --- |
| `input.filter(...), input.filter(...)` | With a cold publisher, may subscribe upstream twice |
| `input.share()` | Typically connects on the first subscriber; late subscribers may miss data |
| `input.publish().autoConnect(2)` | Waits for both subscribers; shares the source, but branches affect each other's backpressure |
| `input.publish().refCount(2)` | Connects once enough subscribers exist and can disconnect when subscriber count drops below threshold |
| `input.cache()` | Replays cached items; must consider memory usage for long or unbounded streams |
| `input.groupBy(key)` | Creates `GroupedFlux` groups by key; does **not** automatically create a new output binding per key |

## 7. Testing both outputs in a single subscription

You can test the `splitOrders` logic directly in Java unit tests without a broker. Example using **JUnit 5** and **reactor-test**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

class OrderRoutingConfigTest {

    @Test
    void routesOrdersAndSubscribesSourceOnce() {
        var first = new OrderRoutingConfig.Order("O-101", 1_500_000L);
        var second = new OrderRoutingConfig.Order("O-102", 230_000L);
        var boundary = new OrderRoutingConfig.Order("O-103", 1_000_000L);

        AtomicInteger upstreamSubscriptions = new AtomicInteger();
        Flux<OrderRoutingConfig.Order> source = Flux
                .just(first, second, boundary)
                .doOnSubscribe(s -> upstreamSubscriptions.incrementAndGet());

        Tuple2<
                Flux<OrderRoutingConfig.Order>,
                Flux<OrderRoutingConfig.Order>
        > outputs = new OrderRoutingConfig().splitOrders().apply(source);

        // Mono.zip subscribes to both branches, meeting autoConnect(2).
        Mono<
                Tuple2<List<String>, List<String>>
        > groupedIds = Mono.zip(
                outputs.getT1().map(OrderRoutingConfig.Order::id).collectList(),
                outputs.getT2().map(OrderRoutingConfig.Order::id).collectList());

        StepVerifier.create(groupedIds)
                .assertNext(groups -> {
                    assertEquals(List.of("O-101", "O-103"), groups.getT1());
                    assertEquals(List.of("O-102"), groups.getT2());
                })
                .verifyComplete();

        assertEquals(1, upstreamSubscriptions.get());
    }
}
~~~

The test verifies **three distinct properties**:

1. **Correct partitioning:** the two high-value orders, including the exact threshold value, go to output 0; the remaining order goes to output 1.
2. **Both branches are subscribed:** `Mono.zip` combines collection from both branches, allowing the shared source to connect.
3. **Source is subscribed to only once:** the `upstreamSubscriptions` counter increments when the input publisher is subscribed.

Only use `collectList()` with **finite** sources like `Flux.just(...)` in tests. If the application runs continuously on a topic, the stream normally never completes and `collectList()` would wait or accumulate items forever. In production, messages are processed item-by-item as the `Flux` emits.

## 8. Sending one event to both outputs

When one channel is needed for business processing and another for auditing, the two branches are **not mutually exclusive**:

~~~java
@Bean
public Function<Flux<OrderRoutingConfig.Order>,
        Tuple2<Flux<OrderRoutingConfig.Order>, Flux<String>>>
        processAndAudit() {

    return input -> {
        Flux<OrderRoutingConfig.Order> shared =
                input.publish().autoConnect(2);

        Flux<OrderRoutingConfig.Order> processing = shared;
        Flux<String> audit = shared.map(order ->
                "ORDER_RECEIVED:" + order.id());

        return Tuples.of(processing, audit);
    };
}
~~~

Now the same order can appear as **two different payloads**:

- `processAndAudit-out-0` emits `Order` for business processing.
- `processAndAudit-out-1` emits `String` for auditing/monitoring.

This is still **one input source, two outputs**. To test event duplication, subscribe to both outputs and assert the item count on each branch. If delivery guarantees to both destinations under failure scenarios are required, check the binder's delivery guarantees and retry strategies; returning two `Flux` streams does not by itself provide atomic transactions across two broker destinations.

## 9. Practical implementation notes

### 9.1. Error handling

A reactive function typically sets up the pipeline once, and records are then processed as the `Flux` emits events. Errors occurring mid-pipeline are emitted as `onError` signals; you cannot automatically expect imperative per-call retry mechanisms to apply to each individual item in a reactive stream.

For invalid orders, decide explicitly whether to drop them, route them to an error branch, log them, send them to a dead-letter destination, or terminate the stream. Consider item-level error handling, such as separating validation and modeling a `Valid/Invalid` result before branching, instead of letting an unexpected exception terminate the subscription.

### 9.2. Payload, headers, and message conversion

In Spring Cloud Stream, each output binding can have its own `content-type` and conversion configuration. If the logic needs to preserve headers such as correlation ID or trace ID, you can use `Message<Order>` payloads or rebuild `Message<?>` with the desired headers. When transforming from `Order` to `String`, **do not assume** all headers from the original message are automatically copied.

The `Tuple2<Flux<A>, Flux<B>>` return contract lets Spring Cloud Function provide type information per output. Actual data must still be compatible with the converter, serializer, and schema of the messaging system.

### 9.3. Output count is fixed in the function contract

`Tuple2` means two **pre-declared** outputs. If the requirement is to create a new topic for each customer ID generated at runtime, a fixed tuple cannot represent a dynamically growing number of outputs. When dynamic destinations are needed, consider routing features or Spring Cloud Stream's `StreamBridge` with an appropriate destination management policy.

### 9.4. Composition and reusability

Within the same application, classification predicates/logic can be reused independently of any broker. `FunctionCatalog` supports looking up and composing type-compatible functional beans; however, the `|` operator in `spring.cloud.function.definition` represents **sequential composition**, not automatically duplicating one input into multiple bindings. When the goal is two destinations, explicitly declare two output streams and configure them via an adapter that supports multiple ports.

HTTP or serverless environments can reuse the classification logic, but **do not automatically support reactive tuples as two HTTP responses or two endpoints**. Multi-port mapping depends on the adapter. Spring Cloud Stream is the natural context for applying this example to event streams.

## 10. Design checklist and self-check exercises

Before putting a stream-splitting function into production, verify:

- [ ] It is clearly defined whether each record should appear on one branch or multiple branches.
- [ ] The signature `Function<Flux<T>, TupleN<Flux<...>>>` accurately describes the port count and payload types.
- [ ] The order of `Tuples.of(...)` matches the `-out-0`, `-out-1` bindings.
- [ ] Both outputs are subscribed to and source sharing matches the adapter's lifecycle.
- [ ] Boundary conditions, invalid records, and the case where one branch emits no items have been considered.
- [ ] Backpressure, errors, retries, and message delivery guarantees have been evaluated at the system level.
- [ ] Tests verify accurate routing without duplicating side effects caused by re-subscribing to the source.

### Exercise 1: Identify outputs

How many output bindings does the following function create under Spring Cloud Function's multi-port model?

~~~java
Function<Flux<Integer>, Tuple2<Flux<Integer>, Flux<String>>>
~~~

**Answer:** **Two** output bindings. `getT1()` emits `Integer`, and `getT2()` emits `String`. The single input `Flux<Integer>` has one input binding.

### Exercise 2: Find the bug in branching

Given a source that emits a finite set of events and completes:

~~~java
Flux<Integer> shared = Flux.just(1, 2, 3)
        .publish()
        .autoConnect(2);

Flux<Integer> odd = shared.filter(n -> n % 2 != 0);
Flux<Integer> even = shared.filter(n -> n % 2 == 0);

odd.collectList().block(); // Called alone
~~~

**What happens?** Only one subscriber exists for `shared`, so the `autoConnect(2)` threshold is not reached. Because the source never connects, `block()` can wait forever. Both branches must be subscribed to concurrently, for example using `Mono.zip(odd.collectList(), even.collectList())` for a finite source.

### Exercise 3: Distinguish split vs. broadcast

Replace the two `filter` conditions in the order example with two different `map` operations on the same `shared` stream, then return `Tuples.of(first, second)`. When both outputs are subscribed to, how many times can each valid event be emitted across all outputs?

**Answer:** **Two representations** of the event can be emitted: one on output 0 and one on output 1. This is output-level fan-out/broadcast, distinct from partitioning where each event enters only one branch.

## References

- [Spring Cloud Function — Programming Model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Functions with multiple input and output arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Reactor Core — Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html)
- [Reactor Core — Flux, an asynchronous sequence of 0 to N items](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html)
