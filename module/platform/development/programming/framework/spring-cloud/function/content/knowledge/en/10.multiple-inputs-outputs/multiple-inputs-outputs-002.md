# Representing Multiple Streams with Reactor Tuples

## 1. The problem: one function working with multiple data streams

In **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), we build business logic as `Supplier`, `Function`, or `Consumer` beans so they can be reused independently of the invocation protocol. `FunctionCatalog` manages function lookup and supports composition and message conversion; adapters can expose the same logic over HTTP, message brokers, or serverless environments.

With an ordinary `Function<String, String>`, identifying the input and output is straightforward. However, event-processing systems often have more complex requirements:

- **Merging streams:** receiving order events from one topic and invoice events from another topic, then emitting a unified stream for analytics.
- **Splitting streams:** receiving a mixed event stream, then sending order events to one destination and all other events to another destination.
- **Multiple sources, multiple targets:** simultaneously consuming streams of different types and emitting results across multiple independent streams.

These problems require describing both **the number of data ports** and **the data type at each port**. Spring Cloud Function uses **Project Reactor** `Tuple` types to represent this for *reactive functions*.

Lesson goals: understand `Tuple2`/`Tuple3`, accurately read `TupleN<Flux<...>>` signatures, build functions that merge or branch streams, and know how these ports are mapped to bindings by Spring Cloud Stream.

## 2. What is a Tuple in Project Reactor?

A **Tuple** is a structure that holds a **fixed** number of elements, each with its own data type. Project Reactor provides these classes in the `reactor.util.function` package:

| Type | Element count | Accessors |
| --- | ---: | --- |
| `Tuple2<A, B>` | 2 | `getT1()`, `getT2()` |
| `Tuple3<A, B, C>` | 3 | `getT1()`, `getT2()`, `getT3()` |
| `Tuple4<A, B, C, D>` | 4 | `getT1()` through `getT4()` |
| `Tuple5` through `Tuple8` | 5 to 8 | `getT1()` through the corresponding position |

Use `Tuples.of(...)` to create a tuple:

~~~java
import reactor.util.function.Tuple2;
import reactor.util.function.Tuple3;
import reactor.util.function.Tuples;

Tuple2<String, Integer> pair = Tuples.of("ORDER-42", 3);

String orderId = pair.getT1();  // "ORDER-42"
Integer itemCount = pair.getT2(); // 3

Tuple3<String, Integer, Boolean> triple =
        Tuples.of("ORDER-42", 3, true);

Boolean paid = triple.getT3();  // true
~~~

In this example, `Tuple2<String, Integer>` holds **two values**. The return type of `getT1()` is known to be `String` and `getT2()` is `Integer`, so the program does not need manual casting. These tuples do not allow `null` elements and provide no methods to mutate individual positions directly after creation.

A tuple is not automatically a reactive stream: `Tuple2<String, Integer>` simply holds two ordinary values. When each element is a `Flux<T>`, the tuple holds **references to multiple publishers/streams**:

~~~java
import reactor.core.publisher.Flux;

Flux<String> orders = Flux.just("O-1", "O-2");
Flux<Long> invoices = Flux.just(101L, 102L);

Tuple2<Flux<String>, Flux<Long>> sources =
        Tuples.of(orders, invoices);

Flux<String> firstStream = sources.getT1();
Flux<Long> secondStream = sources.getT2();
~~~

Key point: `sources` is **one Java object** containing **two streams**; it does not immediately hold consumed records. The items inside each `Flux` are emitted upon subscription, following the publisher's reactive lifecycle.

## 3. Distinguishing three easily confused shapes

The following three types look similar but represent completely different contracts:

| Type | Meaning |
| --- | --- |
| `Tuple2<Order, Invoice>` | One tuple containing **two data objects** |
| `Flux<Tuple2<Order, Invoice>>` | **One stream** where each element is **a pair** of order/invoice |
| `Tuple2<Flux<Order>, Flux<Invoice>>` | **Two independent streams**, the first carrying orders and the second carrying invoices |

Observe the position of `Flux`:

~~~text
Flux<Tuple2<Order, Invoice>>
  └─ one stream
       ├─ (Order #1, Invoice #1)
       ├─ (Order #2, Invoice #2)
       └─ ...

Tuple2<Flux<Order>, Flux<Invoice>>
  ├─ first stream: Order #1, Order #2, ...
  └─ second stream: Invoice #A, Invoice #B, ...
~~~

In particular, `Flux.zip(orderFlux, invoiceFlux)` produces a **`Flux<Tuple2<Order, Invoice>>`**, meaning pairs of items are combined inside **one stream**. Conversely, `Tuples.of(orderFlux, invoiceFlux)` produces a **`Tuple2<Flux<Order>, Flux<Invoice>>`** to keep the two streams separate. `zip` pairs items by emission order and does **not** correlate by order ID; if the streams are unbalanced, unpaired items may remain when one side completes.

A `List<Flux<?>>` can carry multiple publishers, but it does not let the framework know the exact count and specific type of each position in advance via generic type parameters. `TupleN` expresses the count (*arity*) and element types directly in the signature, enabling Spring Cloud Function / Spring Cloud Stream to infer the ports along with data conversion information.

## 4. How to read `TupleN<Flux<...>>` in function signatures

Spring Cloud Function recognizes *function arity* forms for reactive functions, where each `Flux<?>` inside a tuple corresponds to one logical port:

| Function signature | Input ports | Output ports | Interpretation |
| --- | ---: | ---: | --- |
| `Function<Flux<A>, Flux<B>>` | 1 | 1 | Transform one stream |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` | 2 | 1 | Merge two sources into one stream |
| `Function<Flux<A>, Tuple2<Flux<B>, Flux<C>>>` | 1 | 2 | Split one source into two streams |
| `Function<Tuple2<Flux<A>, Flux<B>>, Tuple2<Flux<C>, Flux<D>>>` | 2 | 2 | Two input sources, two output streams |
| `Function<Tuple3<Flux<A>, Flux<B>, Flux<C>>, Flux<D>>` | 3 | 1 | Three input sources, one output stream |

For example, `Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>` has only **one Java parameter** on its `apply` method, yet that parameter is a tuple containing two `Flux` streams. Therefore, at the Spring Cloud Stream integration layer, the function is interpreted as **two input bindings and one output binding**.

Limitation note: the `TupleN` multi-port mechanism is designed for **reactive functions** whose tuple elements are `Flux`. Writing an ordinary `Function<A, Tuple2<B, C>>` does **not automatically** create two output bindings, nor does putting two items in a `List` create two ports. HTTP or serverless adapters do not necessarily map multiple ports the way Spring Cloud Stream does.

## 5. 2 inputs, 1 output example: merging events

A service receives order events of type `String` and invoice IDs of type `Long`. We want to merge them into a single string stream while still distinguishing their origin:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

@Configuration
public class GatherConfiguration {

    @Bean
    public Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
            gatherEvents() {
        return sources -> {
            Flux<String> orders = sources.getT1()
                    .map(id -> "ORDER:" + id);

            Flux<String> invoices = sources.getT2()
                    .map(id -> "INVOICE:" + id);

            return Flux.merge(orders, invoices);
        };
    }
}
~~~

Step-by-step explanation:

1. `sources.getT1()` is the **first stream**, carrying `String` payloads.
2. `sources.getT2()` is the **second stream**, carrying `Long` payloads.
3. Each branch transforms its records into prefixed strings so their origin is clear.
4. `Flux.merge(orders, invoices)` emits data from both sources onto **one output stream**.

~~~text
orders-topic   ──> [ gatherEvents-in-0 ] ──┐
                                          ├── gatherEvents ──> [ gatherEvents-out-0 ] ──> events-topic
invoices-topic ──> [ gatherEvents-in-1 ] ──┘
~~~

When deployed with **Spring Cloud Stream** and a suitable binder, the `application.yml` configuration can look like:

~~~yaml
spring:
  cloud:
    function:
      definition: gatherEvents
    stream:
      bindings:
        gatherEvents-in-0:
          destination: orders-topic
        gatherEvents-in-1:
          destination: invoices-topic
        gatherEvents-out-0:
          destination: events-topic
~~~

The `-in-0` suffix corresponds to `getT1()`, and `-in-1` corresponds to `getT2()`. The `-out-0` suffix represents the single output stream. `Flux.merge` **does not guarantee global ordering across the two sources** and **does not join orders with invoices sharing the same key**. Key-based reconciliation requires additional correlation logic, typically accounting for ordering, latency, memory, and event wait timeouts.

## 6. 1 input, 2 outputs example: routing events

One stream contains multiple record types such as `ORDER:101`, `AUDIT:login`, `ORDER:102`. We want to separate order events from all other events:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class RouteConfiguration {

    @Bean
    public Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>>
            routeEvents() {
        return source -> {
            // Wait for 2 subscribers, then share the same source.
            Flux<String> shared = source.publish().autoConnect(2);

            Flux<String> orderEvents = shared
                    .filter(event -> event.startsWith("ORDER:"));

            Flux<String> otherEvents = shared
                    .filter(event -> !event.startsWith("ORDER:"));

            return Tuples.of(orderEvents, otherEvents);
        };
    }
}
~~~

`Tuples.of(orderEvents, otherEvents)` creates a **tuple with two `Flux<String>` elements**, thereby declaring two independent outputs. The order inside the tuple is critical:

- `getT1()`, which is `orderEvents`, corresponds to `routeEvents-out-0`.
- `getT2()`, which is `otherEvents`, corresponds to `routeEvents-out-1`.

~~~text
events-topic ──> [ routeEvents-in-0 ] ──> routeEvents
                                           ├── [ routeEvents-out-0 ] ──> orders-topic
                                           └── [ routeEvents-out-1 ] ──> others-topic
~~~

The corresponding Spring Cloud Stream configuration (a **separate** example, independent of `gatherEvents`):

~~~yaml
spring:
  cloud:
    function:
      definition: routeEvents
    stream:
      bindings:
        routeEvents-in-0:
          destination: events-topic
        routeEvents-out-0:
          destination: orders-topic
        routeEvents-out-1:
          destination: others-topic
~~~

Given inputs `ORDER:101`, `AUDIT:login`, `ORDER:102`, the `out-0` branch emits the two `ORDER` events; the `out-1` branch emits the `AUDIT` event. **Creating two output bindings does not mean sending every record to both outputs**: the data actually emitted on each branch is determined by the reactive logic.

### Why use `publish().autoConnect(2)`?

Normally, a `Flux` is a *cold publisher*: each subscription can re-trigger the source. If you create two branches via separate `source.filter(...)` calls and both branches are subscribed to, the source may be subscribed to **twice**; when the source involves expensive operations or side effects, this is problematic.

`publish()` turns the source into a shared stream; `autoConnect(2)` connects to the source only when **both branches** have a subscriber. As a result, both branches observe the same connected source. On the other hand, if only one branch is subscribed to, the threshold of 2 is not met and the source **does not emit yet**. Keep this condition in mind when testing or modifying output binding configurations.

In this example, both outputs must be consumed. In production systems, you must also examine error handling, per-branch consumption rates, and backpressure behavior; depending on the binder, not every reactive capability is supported end-to-end all the way to the broker.

## 7. Testing stream routing without a message broker

Because `routeEvents` depends only on `Flux` and `Tuple2`, we can test the logic directly without Kafka or RabbitMQ. Example using JUnit 5 and `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

class RouteConfigurationTest {

    @Test
    void separatesOrdersFromOtherEvents() {
        var function = new RouteConfiguration().routeEvents();

        Tuple2<Flux<String>, Flux<String>> outputs =
                function.apply(Flux.just(
                        "ORDER:101", "AUDIT:login", "ORDER:102"));

        // Mono.zip subscribes to both branches; autoConnect(2) then connects.
        StepVerifier.create(Mono.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList()))
                .assertNext(actual -> {
                    assertEquals(
                            List.of("ORDER:101", "ORDER:102"),
                            actual.getT1());
                    assertEquals(
                            List.of("AUDIT:login"),
                            actual.getT2());
                })
                .verifyComplete();
    }
}
~~~

Notably, `Mono.zip(...)` **subscribes to both branches concurrently** (each branch collects its items via `collectList()`). If you wrote the test by calling `outputs.getT1().collectList().block()` first, the second branch would not yet be subscribed, so an example using `autoConnect(2)` could hang. `collectList()` is appropriate here only because the test source is finite; do not use it to collect an unbounded production stream.

## 8. Extending to Tuple3 and more ports

`Tuple3` works just like `Tuple2`. For example, a function merging three streams of the same type:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple3;

@Bean
public Function<Tuple3<Flux<String>, Flux<String>, Flux<String>>,
        Flux<String>> mergeThreeSources() {
    return sources -> Flux.merge(
            sources.getT1().map(value -> "A:" + value),
            sources.getT2().map(value -> "B:" + value),
            sources.getT3().map(value -> "C:" + value));
}
~~~

This function has three input bindings: `mergeThreeSources-in-0`, `mergeThreeSources-in-1`, `mergeThreeSources-in-2`; and one output binding: `mergeThreeSources-out-0`.

If you need **2 → 2**, the signature can be:

~~~java
Function<
    Tuple2<Flux<OrderEvent>, Flux<InvoiceEvent>>,
    Tuple2<Flux<AcceptedEvent>, Flux<RejectedEvent>>
>
~~~

The signature only describes the port structure; for the function to work, the body must still define how events are consumed from the two inputs and how `AcceptedEvent` / `RejectedEvent` are emitted to the two outputs. There is no automatic rule pairing the first input with the first output.

## 9. Tuples and related concepts: avoiding confusion

| Component | Role | What not to infer |
| --- | --- | --- |
| `Tuple2<Flux<A>, Flux<B>>` | Holds two strongly typed streams | Does not mean pairing each `A` with each `B` |
| `Flux<Tuple2<A, B>>` | One stream emitting pairs of data | Does not create two output bindings |
| `Tuples.of(a, b)` | Creates a fixed tuple containing `a` and `b` | Does not subscribe to or execute the publishers |
| `Flux.merge(a, b)` | Combines items from two publishers into one publisher | Does not join by key, does not guarantee fixed interleaving order |
| `Flux.zip(a, b)` | Pairs items by position into tuples | Does not correlate by business ID |
| `publish().autoConnect(2)` | Shares a source once two subscribers are present | Does not activate if only one subscriber appears |
| `FunctionCatalog` | Looks up, normalizes functional beans, composition, conversion | Does not automatically create physical topics/queues |
| Spring Cloud Stream binder | Maps bindings to messaging destinations | Not a feature built into every HTTP/serverless adapter |

### Common errors and how to handle them

1. **Swapping tuple positions:** `getT1()` is binding index **0**, not 1. Misconfiguring the order can cause inputs to be converted to the wrong type or data to be sent to the wrong destination.
2. **Using a tuple of records instead of a tuple of `Flux`:** `Tuple2<Order, Invoice>` cannot be treated as two streams with independent bindings under this arity mechanism.
3. **Using `zip` when you only want to merge events:** `zip` requires items from all sources to form pairs, whereas `merge` is suitable for combining events without pairing.
4. **Creating two reactive branches while ignoring subscriptions:** Each output has its own subscriber; how the source is shared determines whether both branches receive data properly.
5. **Applying imperative error-handling thinking:** With reactive functions, the adapter typically invokes the function once to set up the pipeline, and items then flow through the `Flux`. Handle errors within the reactive chain (such as `onErrorResume` or appropriate retries), rather than assuming per-invocation imperative retry mechanisms apply identically.
6. **Confusing multiple ports with multiple items:** `Flux<String>` can emit many strings on **one** port, whereas `Tuple2<Flux<String>, Flux<String>>` is **two** ports.

## 10. Fitting into the Spring Cloud Function architecture

When defining a functional bean, the **Java signature** is the business contract. `FunctionCatalog` allows looking up functions by name and provides composition/message conversion; how the function is invoked is determined by the **adapter**.

- With **Spring Cloud Stream**, a tuple of `Flux` instances lets the system determine the number of input/output bindings. The order of tuple elements maps to `-in-0`, `-in-1`, `-out-0`, `-out-1`, etc.
- With **HTTP**, the web adapter typically handles one request and one response via its own mechanism. Do not treat a two-stream tuple as two HTTP endpoints just because the signature uses `Tuple2`.
- With **serverless**, how events and results are mapped is determined by the platform adapter; check which signatures are supported.

Spring Cloud Stream requires an appropriate binder to actually connect to topics/queues. Simply declaring a `TupleN` or a `Function` bean does not create a broker or configure destinations automatically. When messages carry headers and content types, the type inside each `Flux<T>` element also tells the framework the expected payload type so it can perform appropriate conversions; invalid types or schemas still need to be handled.

**Self-check:** Suppose a function has the signature:

~~~java
Function<
    Tuple2<Flux<String>, Flux<Long>>,
    Tuple3<Flux<String>, Flux<Integer>, Flux<Boolean>>
>
~~~

Try answering before checking the solution: how many input and output ports are there? What are the default binding names if the bean is named `dispatch`? What is the type of `getT2()` on the output tuple?

**Answer:** There are **2 input ports and 3 output ports**. The input bindings are `dispatch-in-0`, `dispatch-in-1`; the output bindings are `dispatch-out-0`, `dispatch-out-1`, `dispatch-out-2`. The `getT2()` element of the output tuple has type `Flux<Integer>`. The number of items emitted on each stream depends on the implementation logic, not on the tuple size.

### References

- [Spring Cloud Function — Programming model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Functions with multiple input and output arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — `Tuples` API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuples.html)
- [Project Reactor — `Tuple2` API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
