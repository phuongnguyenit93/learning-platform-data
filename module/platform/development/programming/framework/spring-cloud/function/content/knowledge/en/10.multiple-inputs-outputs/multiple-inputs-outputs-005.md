# Distinguishing Multiple Outputs from a Single Output Containing a Collection

## 1. Why is it easy to confuse "multiple results" with "multiple outputs"?

In **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), business logic is written as `Supplier`, `Function`, and `Consumer` beans so it can be reused across multiple environments. `FunctionCatalog` handles registration, lookup, normalization, composition, and message conversion; HTTP, Spring Cloud Stream, or serverless adapters decide how data is delivered to the function and how results are handled.

In the **Multiple Inputs/Outputs** chapter, a question to answer before designing a function is: **does the function need to produce multiple data items, or does it need to expose multiple independent output ports?**

For example, after receiving an order, the system might:

- Generate **three invoice lines** and return them as a `List<InvoiceLine>`.
- Emit **three event messages** to the same topic.
- Send accepted orders to the `orders.accepted` topic and rejected orders to the `orders.rejected` topic.

These three requirements do not share the same output contract. The first two can be implemented with **one output binding**; the last one typically requires **two output bindings**. Confusing them can cause an application to emit the right number of records to the wrong destination, or mistake a single HTTP response containing an array for two separate event streams.

## 2. Three quantities to keep separate

Do not count elements in the return type and conclude you have that many output bindings. Consider **three dimensions**:

| Dimension | Question answered | Example |
| --- | --- | --- |
| **Output port count** (*output arity*) | How many independent logical streams/targets exist? | `routeOrders-out-0` and `routeOrders-out-1` = **2 ports** |
| **Emitted message count** (*message count*) | How many messages are sent on each port? | One port `audit-out-0` sends 3 messages |
| **Payload item count** (*collection size*) | How many elements does a single message/return value contain? | JSON array `["A", "B", "C"]` contains 3 elements |

To see the difference clearly:

~~~text
A. One output containing a Collection

request ──> Function<Order, List<Line>>
                           |
                           └── out-0 ──> [Line-1, Line-2, Line-3]
                                         1 result containing 3 items

B. One output emitting multiple messages

request ──> Function<String, List<Message<String>>>
                           |
                           └── out-0 ──> message A
                                      ├─> message B
                                      └─> message C
                                         3 messages to the same destination

C. Multiple independent outputs

Flux<Order> ──> Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
                           |
                           ├── out-0 ──> orders.accepted
                           └── out-1 ──> orders.rejected
                                         2 separate targets/bindings
~~~

Element count, message count, and port count **can all differ**. One port can emit millions of messages; one message can contain thousands of items; one function can have multiple ports, each emitting multiple messages.

> **Signature reading rule:** For multi-port reactive functions supported by Spring Cloud Function/Spring Cloud Stream, `TupleN<Flux<...>>` is how multiple ports are represented. A `List`, `Set`, `Collection`, or `Flux` containing multiple items **does not automatically increase the number of output bindings**.

## 3. A function returning a Collection: a single result value

Suppose an order contains multiple product SKUs. A function builds a list of descriptive lines:

~~~java
import java.util.List;
import java.util.function.Function;

public class OrderLogic {

    public record Order(String id, List<String> skus, boolean priority) {}

    public static Function<Order, List<String>> lineLabels() {
        return order -> order.skus().stream()
                .map(sku -> order.id() + ":" + sku)
                .toList();
    }
}
~~~

Usage:

~~~java
OrderLogic.Order order = new OrderLogic.Order(
        "O-101", List.of("SKU-A", "SKU-B", "SKU-C"), false);

List<String> result = OrderLogic.lineLabels().apply(order);
// ["O-101:SKU-A", "O-101:SKU-B", "O-101:SKU-C"]
~~~

The `apply` method is invoked with **one** `Order` object and returns **one** `List<String>` object. The list has three items, yet the Java-level function contract is still **1 input value → 1 output value**.

When returned over HTTP with appropriate JSON serialization, the result can be represented as a **JSON array in a single response**:

~~~json
[
  "O-101:SKU-A",
  "O-101:SKU-B",
  "O-101:SKU-C"
]
~~~

This is **one response containing three elements**, not three HTTP endpoints or three independent responses. How an adapter serializes/unwraps a `Collection` depends on configuration and the invocation environment; by itself, the `Function<Order, List<String>>` signature does not ask the framework to create extra ports.

If the function returns a `Set<String>`, the item count may be smaller than the input count due to deduplication; if it returns a `Map<String, Result>`, the data has multiple entries. Still, **Collection size is always independent of output port count**.

### 3.1. A Collection is a value; a Flux is a publisher

Compare:

~~~java
Function<Order, List<String>> makeLabels;

Function<Flux<Order>, Flux<String>> emitLabels;

Function<Flux<Order>, Flux<List<String>>> emitLabelBatches;
~~~

| Signature | Interpretation |
| --- | --- |
| `Function<Order, List<String>>` | Each function call returns one `List` |
| `Function<Flux<Order>, Flux<String>>` | One output stream, emitting individual `String` items |
| `Function<Flux<Order>, Flux<List<String>>>` | One output stream, where each emitted item is itself a `List<String>` |

In all three cases, **there is only one logical output port**. Specifically in reactive code, each `onNext` signal of `Flux<List<String>>` carries a list; you cannot automatically treat the elements inside that list as separate output bindings.

Example turning one order into multiple `onNext` signals on **one** `Flux`:

~~~java
import reactor.core.publisher.Flux;

Function<Flux<OrderLogic.Order>, Flux<String>> emitLabels =
        orders -> orders.flatMapIterable(order ->
                order.skus().stream()
                        .map(sku -> order.id() + ":" + sku)
                        .toList());
~~~

If the input includes an order with three SKUs, `emitLabels` emits three consecutive strings on **the same output**. When wired through Spring Cloud Stream with an appropriate adapter/binder, each item in the stream can be sent as a separate message on the same output binding. That is **expanding event count**, not increasing *arity*.

## 4. Special case in Spring Cloud Stream: List<Message<T>>

Spring Cloud Stream has a **batch producer** feature: when a function returns `List<Message<T>>`, the binder can send **each `Message` in the list as a separate message** to **the same output destination**. The Spring Cloud Stream documentation directly illustrates this case.

Example generating three audit messages from one order ID:

~~~java
import java.util.List;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class AuditBatchConfiguration {

    @Bean
    public Function<String, List<Message<String>>> emitAuditEvents() {
        return id -> List.of(
                MessageBuilder.withPayload("RECEIVED:" + id)
                        .setHeader("eventType", "received").build(),
                MessageBuilder.withPayload("VALIDATED:" + id)
                        .setHeader("eventType", "validated").build(),
                MessageBuilder.withPayload("QUEUED:" + id)
                        .setHeader("eventType", "queued").build());
    }
}
~~~

If the input is `"O-101"`, the returned list contains three `Message<String>` objects. Under the batch producer mechanism described above, the result is:

~~~text
                         ┌─> "RECEIVED:O-101"
emitAuditEvents-out-0 ────┼─> "VALIDATED:O-101"   (same destination)
                         └─> "QUEUED:O-101"

Output binding count: 1
Emitted message count: 3
~~~

Example `application.yml` for the **single function** `emitAuditEvents`:

~~~yaml
spring:
  cloud:
    function:
      definition: emitAuditEvents
    stream:
      bindings:
        emitAuditEvents-in-0:
          destination: orders.audit.requested
        emitAuditEvents-out-0:
          destination: orders.audit.events
~~~

All three messages go to `orders.audit.events` through **one binding** named `emitAuditEvents-out-0`. They are **not** automatically routed sequentially to `-out-0`, `-out-1`, `-out-2`.

**Important boundary to keep accurate:** Splitting each `Message` inside `List<Message<T>>` is behavior documented for **Spring Cloud Stream's batch producer**. Do not assume **every** HTTP/serverless adapter, or **every** Collection such as `List<String>`, `Set<String>`, or `List<Order>`, must emit each element as a separate message. That behavior depends on how the adapter handles the return type.

When returning an empty Collection, the actual message count can be zero even though the output binding still exists. When returning a long list, the message count can be large, yet the binding count remains unchanged.

### 4.1. Does a "Batch consumer" increase the number of input bindings?

No. Spring Cloud Stream also supports a **batch consumer** for binders capable of delivering batches when batch mode is enabled:

~~~java
@Bean
public Function<List<String>, Integer> countBatch() {
    return List::size;
}
~~~

Example enabling it on the input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: countBatch
    stream:
      bindings:
        countBatch-in-0:
          destination: orders.in
          consumer:
            batch-mode: true
        countBatch-out-0:
          destination: orders.count
~~~

`List<String>` on the **input** represents a batch of multiple payloads, yet there is still only **one input binding**, `countBatch-in-0`. Depending on the binder, per-message headers inside a batch are organized in binder-specific ways; consult the binder documentation when working with metadata.

Batch producer/consumer and multiple input/output bindings address **two different design axes**: batching is how **messages** are grouped or split on a single port; bindings are how **streams** connect to the outside world.

## 5. True multiple outputs: Tuple2<Flux<A>, Flux<B>>

If the requirement is for one group of events to go to topic `orders.priority` and another group to go to topic `orders.standard`, merely returning `List<Order>` cannot express two independent destinations.

We declare a **reactive function** returning a tuple of two publishers:

~~~java
import java.util.List;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class OrderRoutingConfiguration {

    public record Order(String id, List<String> skus, boolean priority) {}

    @Bean
    public Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
            routeOrders() {
        return source -> {
            // Both branches share upstream after both subscribe.
            Flux<Order> shared = source.publish().autoConnect(2);

            Flux<Order> priorityOrders = shared.filter(Order::priority);
            Flux<Order> standardOrders =
                    shared.filter(order -> !order.priority());

            return Tuples.of(priorityOrders, standardOrders);
        };
    }
}
~~~

Here `Tuple2` has two `Flux<Order>` elements. Spring Cloud Function recognizes **1 → 2 function arity** in the reactive context, allowing Spring Cloud Stream to create and use two output bindings:

| Binding | Tuple element | Meaning |
| --- | --- | --- |
| `routeOrders-in-0` | `Flux<Order> source` | Incoming order stream |
| `routeOrders-out-0` | `Tuple2.getT1()` | Priority order stream |
| `routeOrders-out-1` | `Tuple2.getT2()` | Standard order stream |

Separate `application.yml` configuration for `routeOrders`:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrders
    stream:
      bindings:
        routeOrders-in-0:
          destination: orders.received
        routeOrders-out-0:
          destination: orders.priority
        routeOrders-out-1:
          destination: orders.standard
~~~

~~~text
orders.received
      |
      v
 routeOrders
      |
      +-- getT1() --> routeOrders-out-0 --> orders.priority
      |
      +-- getT2() --> routeOrders-out-1 --> orders.standard
~~~

With these input orders:

~~~java
new OrderRoutingConfiguration.Order("O-101", List.of("A"), true);
new OrderRoutingConfiguration.Order("O-102", List.of("B", "C"), false);
new OrderRoutingConfiguration.Order("O-103", List.of("D"), true);
~~~

Branch `out-0` emits **two** orders, `O-101` and `O-103`. Branch `out-1` emits **one** order, `O-102`. The total event count is three, while the **binding count is two**, declared by `Tuple2<Flux<Order>, Flux<Order>>`. The SKU list **inside** each `Order` does not affect the port count.

### 5.1. Why pay attention to subscriptions?

Since `Flux` is a *cold publisher*, if you write:

~~~java
Flux<Order> priority = source.filter(Order::priority);
Flux<Order> standard = source.filter(order -> !order.priority());
return Tuples.of(priority, standard);
~~~

when the two outputs are subscribed to, they can create **two independent subscriptions** to `source`, causing queries to re-run, side effects to repeat, or data to be received twice.

`source.publish().autoConnect(2)` creates a shared source that connects upstream only after **two subscribers** are present. This pattern fits when the adapter subscribes to **both outputs**. If only one output is subscribed to, the source will **not** connect yet and may emit no data. When building production systems, consider subscriber lifecycles, backpressure, and the impact when one branch is slow or errors out.

If the goal is for **one message to be sent to both destinations**, both branches can use `shared` without mutually exclusive `filter` conditions:

~~~java
Flux<Order> primary = shared;
Flux<Order> audit = shared;
return Tuples.of(primary, audit);
~~~

Then every event can be emitted across **both bindings**. However, two independent destinations do not automatically form an atomic transaction across brokers or guarantee that both targets succeed simultaneously.

## 6. Comparing easily misunderstood signatures

| Java signature | Logical output binding count | Items/messages that can be emitted |
| --- | ---: | --- |
| `Function<Order, List<Line>>` | 1 | One `List` value containing multiple `Line` items; adapter decides transport |
| `Function<String, List<Message<String>>>` | 1 | Spring Cloud Stream batch producer can send each `Message` on the same binding |
| `Function<Flux<Order>, Flux<Line>>` | 1 | Multiple `Line` items as multiple `onNext` signals on one stream |
| `Function<Flux<Order>, Flux<List<Line>>>` | 1 | Multiple `List` values emitted on the same stream |
| `Function<Flux<Order>, Flux<Tuple2<A, B>>>` | 1 | Each item on one stream is a tuple of values |
| `Function<Flux<Order>, Tuple2<Flux<A>, Flux<B>>>` | **2** | Two independent streams, each able to emit 0..N items |
| `Function<Flux<Order>, Tuple3<Flux<A>, Flux<B>, Flux<C>>>` | **3** | Three independent streams |
| `Function<Order, Tuple2<A, B>>` | 1 in single-value return model | Returns one tuple object; **not automatically** reactive multi-output |

**Two shapes differing by `Flux` placement:**

~~~java
// ONE stream, where each element is a pair.
Flux<Tuple2<String, Integer>>

// TWO streams, each carrying its own element type.
Tuple2<Flux<String>, Flux<Integer>>
~~~

In particular, `Tuple2<List<A>, List<B>>` is still just **one tuple holding two lists** as a Java value. Do not infer two output bindings just because an object holds two fields or two Collections. Multi-binding function arity support in Spring Cloud Function is defined for **reactive functions with tuples of `Flux`**, and support levels depend on the adapter.

## 7. Testing: item count differs from output count

We can verify both models before connecting a broker.

### 7.1. Testing a Collection returned as a single value

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderLogicTest {

    @Test
    void createsOneListWithThreeItems() {
        var order = new OrderLogic.Order(
                "O-101", List.of("A", "B", "C"), true);

        List<String> labels = OrderLogic.lineLabels().apply(order);

        assertEquals(3, labels.size());
        assertEquals(
                List.of("O-101:A", "O-101:B", "O-101:C"),
                labels);
    }
}
~~~

The result contains three `String` elements, yet `OrderLogic.lineLabels()` remains a `Function<Order, List<String>>` with **one return value**.

### 7.2. Testing two reactive branches

Example using JUnit 5 and `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

class OrderRoutingConfigurationTest {

    @Test
    void sendsOrdersToTwoIndependentOutputs() {
        var first = new OrderRoutingConfiguration.Order(
                "O-101", List.of("A"), true);
        var second = new OrderRoutingConfiguration.Order(
                "O-102", List.of("B", "C"), false);
        var third = new OrderRoutingConfiguration.Order(
                "O-103", List.of("D"), true);

        var function = new OrderRoutingConfiguration().routeOrders();
        Tuple2<Flux<OrderRoutingConfiguration.Order>,
                Flux<OrderRoutingConfiguration.Order>> outputs =
                function.apply(Flux.just(first, second, third));

        // Both branches are subscribed concurrently so autoConnect(2) activates.
        StepVerifier.create(Mono.zip(
                        outputs.getT1()
                                .map(OrderRoutingConfiguration.Order::id)
                                .collectList(),
                        outputs.getT2()
                                .map(OrderRoutingConfiguration.Order::id)
                                .collectList()))
                .assertNext(groups -> {
                    assertEquals(
                            List.of("O-101", "O-103"), groups.getT1());
                    assertEquals(
                            List.of("O-102"), groups.getT2());
                })
                .verifyComplete();
    }
}
~~~

The test demonstrates **two output publishers**; together they emit three orders, while the port count is two. `Mono.zip` is used to **collect results from both branches concurrently in the test**, without creating any additional bindings. `collectList()` should only be used on finite sources in tests; a continuous production stream may never complete.

### 7.3. Testing a single-output batch producer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

class AuditBatchConfigurationTest {

    @Test
    void returnsThreeMessagesForTheSameOutput() {
        List<Message<String>> messages =
                new AuditBatchConfiguration()
                        .emitAuditEvents().apply("O-101");

        assertEquals(3, messages.size());
        assertEquals("RECEIVED:O-101", messages.get(0).getPayload());
        assertEquals("VALIDATED:O-101", messages.get(1).getPayload());
        assertEquals("QUEUED:O-101", messages.get(2).getPayload());
    }
}
~~~

This test verifies that the function produces **three `Message` instances**. To verify how the binder sends each message to **one destination**, integration tests with Spring Cloud Stream and an appropriate binder are needed. Do not treat a Java unit test as proof that topics are configured or messages were delivered successfully.

## 8. Choosing a design for real-world requirements

| Requirement | Recommended model |
| --- | --- |
| Return a list of results to an HTTP caller | `Function<I, List<O>>`; adapter serializes as a single appropriate response |
| Emit multiple events to the same topic from one stream | `Function<Flux<I>, Flux<O>>`, using `flatMap`/`flatMapIterable` as needed |
| Produce multiple `Message` instances from one input to the **same** destination | `Function<I, List<Message<O>>>` with Spring Cloud Stream batch producer |
| Route results to two different topics | Reactive `Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>` |
| Route results to three different topics | Reactive `Function<Flux<I>, Tuple3<Flux<A>, Flux<B>, Flux<C>>>` |
| Destination changes dynamically per message | Consider routing/`StreamBridge` per Spring Cloud Stream capabilities |
| Receive a batch of messages per call and process as a list | `Function<List<I>, O>` with binder-supported batch consumer |

### Four common mistakes

1. **Counting Collection elements as ports.** A `List` with 20 items can still be a single return value of a function.
2. **Confusing multiple messages on the same binding with multiple destinations.** Spring Cloud Stream's batch producer can send each `Message` individually, but the output name is still `functionName-out-0`.
3. **Switching `Flux<Tuple2<A, B>>` to `Tuple2<Flux<A>, Flux<B>>` without evaluating the semantics.** The former describes one stream of pairs; the latter represents two streams that may need separate subscriptions and backpressure handling.
4. **Assuming every adapter understands reactive tuples like Spring Cloud Stream.** HTTP/serverless may follow a different request-response model. Multi-binding support must be verified per adapter.

### Connecting with FunctionCatalog and composition

`FunctionCatalog` can look up beans by name, normalize signatures, and support type/message conversion as well as composition between type-compatible functions. However:

- Composing `a|b` is **sequentially invoking** `b` with the output of `a`; it does not automatically turn a `List` into multiple output bindings.
- Having multiple items in a `List` does not mean the system automatically configures multiple binder destinations.
- For true multiple outputs, the reactive `TupleN<Flux<...>>` structure and binding configuration are part of the **integration contract**, not merely a data detail.

This distinction ensures the same business logic can be reused across HTTP, events, or serverless while accurately describing the **return value**, **message count**, and **target destination** for each environment.

## 9. Self-check exercises

**Question 1.** `Function<String, List<String>>` returns a list of 100 strings. Does it automatically create 100 output bindings?

**Answer:** No. That is a single `List<String>` result. How those 100 items are transmitted/serialized depends on the adapter; the binding count is not inferred from list length.

**Question 2.** In Spring Cloud Stream, `Function<String, List<Message<String>>>` returns two messages and has `-out-0` configured to point to `audit.events`. How many output bindings are there?

**Answer:** **One** output binding, `-out-0`. The batch producer can send **two separate messages** to the same `audit.events` destination.

**Question 3.** How many outputs does `Function<Flux<Order>, Tuple2<Flux<Accepted>, Flux<Rejected>>>` have?

**Answer:** **Two** output bindings, corresponding to `-out-0` and `-out-1` when the adapter supports the reactive function arity model.

**Question 4.** `Function<Flux<Order>, Flux<List<Line>>>` emits 50 lists on one `Flux`. How many output bindings are there? How many `onNext` signals are emitted?

**Answer:** **One** output binding; **50** `onNext` signals are emitted, each carrying a `List<Line>`. The total number of `Line` elements across the 50 lists can be greater than 50.

**Question 5.** You need to send an event to two topics `orders.main` and `orders.audit`. Is returning `List<Message<Order>>` with two messages enough to create two bindings?

**Answer:** No. You must design routing to two independent destinations: for example, two outputs `Tuple2<Flux<Order>, Flux<Order>>` in Spring Cloud Stream, or a supported dynamic routing mechanism. Two elements in a `List<Message<Order>>` under the batch producer still belong to **one output binding**.

## References

- [Spring Cloud Function — Programming Model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages (Batch Producers, Batch Consumers)](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional binding, binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
