# Mapping Indices to Spring Cloud Stream Bindings

## 1. Why is index mapping needed?

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), business logic is written as `Supplier`, `Function`, or `Consumer` beans. These beans can be looked up through `FunctionCatalog`, chained via composition, and receive type-converted data, allowing logic to be reused across HTTP, events, or serverless environments depending on the adapter.

When deployed with **Spring Cloud Stream**, the framework connects function inputs and outputs to the messaging system through constructs called **bindings**. A function may have a single input/output, or it can have **multiple ports** when using reactive functions with `TupleN<Flux<...>>`. In that case, the framework needs a consistent rule to determine which destination the **first port**, **second port**, etc., are configured to use.

For example, a service consumes:

- Order creation events from the `orders.created` topic.
- Payment confirmation events from the `payments.confirmed` topic.

The service emits:

- Order indexes to the `orders.indexed` topic.
- Payment indexes to the `payments.indexed` topic.

~~~text
                  indexEvents
               ┌─────────────────┐
orders.created ───► in-0         out-0 ───► orders.indexed
               │                 │
payments.confirmed ► in-1       out-1 ───► payments.indexed
               └─────────────────┘
~~~

For the application to work properly, we must understand:

1. How **port indices** are assigned.
2. How **binding names** are formed from the function name and index.
3. How a **destination** on the broker is specified for each binding.
4. How `Tuple2`/`Tuple3` element positions relate to `-in-0`, `-in-1`, `-out-0`, `-out-1`.

> **Scope:** This lesson covers functional bindings in **Spring Cloud Stream**. Do not assume the same reactive tuple will automatically create multiple HTTP endpoints or multiple serverless outputs; mapping depends on the adapter.

## 2. Distinguishing function name, binding name, and destination

These three concepts are related but distinct:

| Concept | Example | Role |
| --- | --- | --- |
| **Function/bean name** | `indexEvents` | Name of the Spring-registered function selected for binding |
| **Binding name** | `indexEvents-in-0` | Port identifier inside Spring Cloud Stream configuration |
| **Destination** | `orders.created` | Topic, queue, exchange, or physical/logical target managed by the binder |

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: indexEvents
    stream:
      bindings:
        indexEvents-in-0:
          destination: orders.created
~~~

`spring.cloud.function.definition` specifies which function is activated in the messaging configuration. `indexEvents-in-0` is the **binding name**; `orders.created` is the **destination name**. Changing a topic name does not require changing the bean name or the port index.

If `destination` is omitted, Spring Cloud Stream defaults to using the **binding name** as the destination. That default can cause an application to accidentally connect to a topic named `indexEvents-in-0`; therefore, explicitly configure `destination` in real business examples.

### A binding is not a record or a data field

A binding can carry **many messages** over time. A single message can in turn carry a `List<T>` payload or an object with many fields. The **binding index** counts **ports**, not messages, payload fields, or broker partitions.

## 3. Default binding naming convention

Spring Cloud Stream uses this convention for the functional model:

~~~text
<functionName>-in-<index>
<functionName>-out-<index>
~~~

Where `index` is an integer starting at **0**, counted separately for inputs and outputs. For a function named `indexEvents`:

| Logical port | Default binding | Index |
| --- | --- | ---: |
| First input | `indexEvents-in-0` | 0 |
| Second input | `indexEvents-in-1` | 1 |
| First output | `indexEvents-out-0` | 0 |
| Second output | `indexEvents-out-1` | 1 |

Note two points:

- The `-0` suffix does **not** mean the port is disabled or carries the value zero. It is simply the index of the **first port**.
- Input and output have **two independent index sequences**. Having `-in-1` does not imply `-out-1` must exist; the port counts on the two sides can differ.

### For standard Supplier, Function, and Consumer

| Bean | Contract | Default bindings |
| --- | --- | --- |
| `Supplier<O> create()` | No input, one output | `create-out-0` |
| `Function<I, O> convert()` | One input, one output | `convert-in-0`, `convert-out-0` |
| `Consumer<I> record()` | One input, no returned output | `record-in-0` |

These examples assume Spring Cloud Stream is binding the corresponding beans. `Supplier` polling frequency, producing output messages from a `Consumer`, and error handling follow adapter/binder rules; the binding name itself only describes **the logical data path**.

## 4. From Reactor Tuple position to binding index

For multi-port reactive functions, **Spring Cloud Function** uses **Project Reactor**'s `TupleN` types, where each element is a `Flux`. Example signature:

~~~java
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>>
~~~

Meaning:

- The **input** `Tuple2` holds **two input streams**.
- The **output** `Tuple2` holds **two output streams**.
- Each `Flux<T>` specifies the payload type of one port.

**The easiest trap to fall into** is that Reactor names accessors `getT1()`, `getT2()` (**1-based**), whereas bindings use **0-based** indices.

| Tuple position | Reactor accessor | Input binding | Output binding |
| --- | --- | --- | --- |
| First element | `getT1()` | `indexEvents-in-0` | `indexEvents-out-0` |
| Second element | `getT2()` | `indexEvents-in-1` | `indexEvents-out-1` |
| Third element, if `Tuple3` | `getT3()` | `other-in-2` | `other-out-2` |

**Rule:** element `getTn()` corresponds to binding index `n - 1`, with input and output sides evaluated independently.

~~~java
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

Tuple2<Flux<String>, Flux<Long>> inputs = Tuples.of(
        Flux.just("ORDER-101"), // T1 -> in-0
        Flux.just(250_000L));   // T2 -> in-1

Flux<String> orders = inputs.getT1();
Flux<Long> payments = inputs.getT2();
~~~

The order in `Tuples.of(...)` on the **output** has the same meaning: the first element maps to `-out-0`, and the second element maps to `-out-1`.

### Do not equate binding order with business rules

One function can merge input 0 and input 1 into **one** output 0. Another function can take **one** input 0 and split it into output 0 and output 1. Port ordering does **not** enforce a rule that "input 0 must produce output 0"; that just happens to be how some examples are structured.

## 5. Complete Java example: two inputs and two outputs

The example below uses **Java 17+** (`record`), Spring Cloud Function, Spring Cloud Stream, and Reactor. The two sources have different payload types; the function produces two independent result streams:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class EventIndexConfiguration {

    public record OrderCreated(String orderId, long totalVnd) {}

    public record PaymentConfirmed(String orderId, long paidVnd) {}

    public record OrderIndex(String orderId, long totalVnd) {}

    public record PaymentIndex(String orderId, boolean paid) {}

    @Bean
    public Function<
            Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
            Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>>
            indexEvents() {
        return inputs -> {
            // First input: indexEvents-in-0.
            Flux<OrderCreated> orders = inputs.getT1();

            // Second input: indexEvents-in-1.
            Flux<PaymentConfirmed> payments = inputs.getT2();

            Flux<OrderIndex> orderIndexes = orders.map(order ->
                    new OrderIndex(order.orderId(), order.totalVnd()));

            Flux<PaymentIndex> paymentIndexes = payments.map(payment ->
                    new PaymentIndex(
                            payment.orderId(), payment.paidVnd() > 0));

            // T1 -> indexEvents-out-0, T2 -> indexEvents-out-1.
            return Tuples.of(orderIndexes, paymentIndexes);
        };
    }
}
~~~

Reading the exact contract:

| Position | Binding name | Payload type |
| --- | --- | --- |
| `inputs.getT1()` | `indexEvents-in-0` | `OrderCreated` |
| `inputs.getT2()` | `indexEvents-in-1` | `PaymentConfirmed` |
| First element of `Tuples.of(...)` | `indexEvents-out-0` | `OrderIndex` |
| Second element of `Tuples.of(...)` | `indexEvents-out-1` | `PaymentIndex` |

This function does **not** pair an order with a payment; each stream is transformed independently. If the business logic requires reconciling two sources by `orderId`, you must add appropriate synchronization/correlation logic, such as a windowed join or keyed state storage. Having two inputs does not make the framework automatically pair messages at the same position or with the same ID.

## 6. Configuring each port to each destination

For the `indexEvents` bean above, the following `application.yml` configuration can be used:

~~~yaml
spring:
  cloud:
    function:
      definition: indexEvents
    stream:
      bindings:
        indexEvents-in-0:
          destination: orders.created
          group: event-indexer
          content-type: application/json
        indexEvents-in-1:
          destination: payments.confirmed
          group: event-indexer
          content-type: application/json
        indexEvents-out-0:
          destination: orders.indexed
          content-type: application/json
        indexEvents-out-1:
          destination: payments.indexed
          content-type: application/json
~~~

Each key under `spring.cloud.stream.bindings` is a **binding name**; the `destination` property underneath is the **target on the broker**. The `group` property applies to **consumer/input bindings**, not output producers. In this example, both input ports use the group name `event-indexer`, yet each port connects to **a separate destination**; they are not merged into a single input.

To run with Kafka or RabbitMQ, the project needs Spring Cloud Stream and the corresponding **binder**, broker connection settings, and appropriate dependencies. The configuration above illustrates the binding contract; it does not provision or create a physical broker.

### Why declare content-type?

`OrderCreated` and `PaymentConfirmed` can both be transmitted as `application/json`, yet they are **two different Java types**. The framework uses the generic type information of each `Flux<T>` along with message conversion metadata to handle payloads properly.

Example JSON on `orders.created`:

~~~json
{"orderId":"O-101","totalVnd":500000}
~~~

JSON on `payments.confirmed`:

~~~json
{"orderId":"O-101","paidVnd":500000}
~~~

Swapping the two `destination` values causes input 0's payload to be incompatible with `OrderCreated` or results in missing/corrupted data; sharing `content-type: application/json` does **not** make the Java types interchangeable. When sending `Message<T>`, consider both headers and payload, as headers do not create new ports.

## 7. Quick overview of multi-input/output patterns

The binding count is derived from the function's **arity**, not from the number of records passing through a `Flux`:

| Reactive function signature | Input bindings | Output bindings |
| --- | --- | --- |
| `Function<Flux<A>, Flux<B>>` | `f-in-0` | `f-out-0` |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` | `f-in-0`, `f-in-1` | `f-out-0` |
| `Function<Flux<A>, Tuple2<Flux<B>, Flux<C>>>` | `f-in-0` | `f-out-0`, `f-out-1` |
| `Function<Tuple2<Flux<A>, Flux<B>>, Tuple2<Flux<C>, Flux<D>>>` | `f-in-0`, `f-in-1` | `f-out-0`, `f-out-1` |
| `Function<Tuple3<Flux<A>, Flux<B>, Flux<C>>, Flux<D>>` | `f-in-0`, `f-in-1`, `f-in-2` | `f-out-0` |

In this table, the bean name is assumed to be `f`. Whether `Flux<A>` emits 1 or 100,000 items does **not** change the number of bindings.

### 2 → 1 example: merging multiple sources

~~~java
@Bean
public Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
        mergeEvents() {
    return sources -> Flux.merge(
            sources.getT1().map(id -> "ORDER:" + id),
            sources.getT2().map(id -> "PAYMENT:" + id));
}
~~~

The logical ports are `mergeEvents-in-0`, `mergeEvents-in-1`, and `mergeEvents-out-0`. `Flux.merge` combines items into one stream, but does **not** automatically pair them by business key.

### 1 → 2 example: branching by rule

~~~java
@Bean
public Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>>
        splitEvents() {
    return input -> {
        Flux<String> shared = input.publish().autoConnect(2);
        Flux<String> orders = shared.filter(s -> s.startsWith("ORDER:"));
        Flux<String> other = shared.filter(s -> !s.startsWith("ORDER:"));
        return Tuples.of(orders, other);
    };
}
~~~

The logical ports are `splitEvents-in-0`, `splitEvents-out-0`, and `splitEvents-out-1`. This example assumes **both outputs have subscribers** so that `autoConnect(2)` connects to the source; if one output is not subscribed to, the source may never start emitting. Evaluate subscription/backpressure behavior across branches according to your binder and application.

The two snippets above are **independent function examples**: select only `mergeEvents` or `splitEvents` in `spring.cloud.function.definition` when deploying. If an application has multiple bindable beans, explicitly declare the function to activate.

## 8. Renaming bindings while keeping indices intact

Spring Cloud Stream can **rename** a default binding to a more descriptive name via:

~~~properties
spring.cloud.stream.function.bindings.<implicit-binding-name>=<new-binding-name>
~~~

Example renaming two of `indexEvents`'s four bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: indexEvents
    stream:
      function:
        bindings:
          indexEvents-in-0: incomingOrders
          indexEvents-out-1: outgoingPayments
      bindings:
        incomingOrders:
          destination: orders.created
        indexEvents-in-1:
          destination: payments.confirmed
        indexEvents-out-0:
          destination: orders.indexed
        outgoingPayments:
          destination: payments.indexed
~~~

**Interpretation:**

- `indexEvents-in-0` is still input port index 0, but the binding name used for configuration is `incomingOrders`.
- `indexEvents-out-1` is still output port index 1, but the binding name used for configuration is `outgoingPayments`.
- The two unrenamed bindings continue to use `indexEvents-in-1` and `indexEvents-out-0`.
- `getT1()` and `getT2()` in Java **do not change positions** because binding renaming is purely a name mapping.

Once renamed, all properties under `spring.cloud.stream.bindings` (such as `destination`, `group`, `content-type`) for that port must use the **new name**. If you keep configuring `indexEvents-in-0.destination` after renaming it to `incomingOrders`, that property will no longer apply to the intended binding.

The Spring Cloud Stream documentation recommends weighing whether renaming is necessary: it gives bindings business-meaningful names, but adds an extra indirection layer. For applications without legacy naming constraints, **keeping the default names** is usually easier to trace in configuration.

### Binding name differs from destination name

Suppose two environments use the same bean and binding `indexEvents-in-0`, but different topics:

~~~yaml
# Development environment
spring:
  cloud:
    stream:
      bindings:
        indexEvents-in-0:
          destination: dev.orders.created
~~~

~~~yaml
# Production environment: separate replacement configuration
spring:
  cloud:
    stream:
      bindings:
        indexEvents-in-0:
          destination: prod.orders.created
~~~

The binding index remains **0** and Java still uses `getT1()`. Only the actual target connected by the binder changes. These two YAML blocks are **two configuration options for two environments**, not two blocks to append sequentially into the same file.

## 9. Special cases for binding names

### 9.1. Multiple function definitions or composition

`spring.cloud.function.definition` selects which function to bind. With multiple beans, declaring the name explicitly avoids picking the wrong one. When using composition, for example:

~~~properties
spring.cloud.function.definition=normalizeOrder|enrichOrder
~~~

rely on **the composed function's binding names actually created by Spring Cloud Stream**. Do not assume the bindings belonging to each individual bean still exist as they would when bound independently. Composition **sequentially chains outputs** and can alter the externally visible I/O contract.

### 9.2. Explicit bindings declared without directly attaching to a function

Spring Cloud Stream also supports creating **explicit bindings** or sending data via `StreamBridge`. Those bindings may have names that do not follow the `functionName-in-0`/`functionName-out-0` pattern, because they are not inferred directly from a functional bean's signature.

Accordingly, the indexing rules in this lesson apply to **functional bindings generated by the framework from a function**. When you encounter a name like `auditEvents` in `spring.cloud.stream.output-bindings` or `StreamBridge.send("auditEvents", ...)`, treat it as a different binding mechanism and check the corresponding configuration.

### 9.3. Do not confuse with the Kafka Streams Binder

The Kafka Streams Binder adds `KStream`, `KTable`, and different function declaration styles. Although it shares similar binding naming conventions, the examples in this lesson are written for **Spring Cloud Function reactive `Flux` with a Spring Cloud Stream messaging binder**. When switching to the Kafka Streams API, check the signatures and conventions specific to that binder.

## 10. Testing port ordering and configuration

A unit test can confirm that the input tuple is read in the right order and the output tuple preserves the right order. Example using **JUnit 5** and `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class EventIndexConfigurationTest {

    @Test
    void keepsTheTwoInputAndOutputPositions() {
        var function = new EventIndexConfiguration().indexEvents();

        var outputs = function.apply(Tuples.of(
                Flux.just(new EventIndexConfiguration.OrderCreated(
                        "O-101", 500_000L)),
                Flux.just(new EventIndexConfiguration.PaymentConfirmed(
                        "O-101", 500_000L))));

        StepVerifier.create(Mono.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList()))
                .assertNext(both -> {
                    assertEquals(
                            List.of(new EventIndexConfiguration.OrderIndex(
                                    "O-101", 500_000L)),
                            both.getT1());
                    assertEquals(
                            List.of(new EventIndexConfiguration.PaymentIndex(
                                    "O-101", true)),
                            both.getT2());
                })
                .verifyComplete();
    }
}
~~~

This test only verifies **Java logic and tuple ordering**. To confirm that topics/queues are wired properly, write an integration test with the **Spring Cloud Stream Test Binder** or your configured messaging binder. When doing so:

1. Send an `OrderCreated` message to the binding matching `indexEvents-in-0` and `PaymentConfirmed` to `indexEvents-in-1`.
2. Receive results from `indexEvents-out-0` and `indexEvents-out-1`.
3. Verify contents, payload types, and that each result reaches the right destination.
4. Repeat when binding renaming is configured to confirm properties use the new names.

Only use `collectList()` on **finite** test data like `Flux.just(...)`. For continuous topics, a `Flux` stream does not necessarily complete, and `collectList()` can hold data in memory indefinitely.

### Inspecting running bindings

If the project enables Actuator and the Spring Cloud Stream `bindings` endpoint with appropriate configuration, you can inspect the managed bindings. Whether the endpoint is available, exposed, and which operations are supported depends on version and security configuration; do not assume it is always enabled.

When diagnosing issues at runtime, prioritize checking **these four exact details**: selected bean name, binding name, actual destination, and payload type. Looking only at topic names while ignoring the mapping easily hides indexing bugs.

## 11. Common configuration mistakes

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Payment messages enter the order branch | Swapped `destination` on `-in-0` and `-in-1` | Cross-check `getT1()`/`getT2()` types against bindings |
| Output 0's payload appears on output 1's topic | Swapped order in `Tuples.of(...)` or output config | Verify output `getT1()` ↔ `-out-0` |
| No messages received even though app starts | Wrong `definition`, wrong destination, or binder disconnected | Check selected bean, binding name, broker, and logs |
| Renamed binding but destination change has no effect | Still configuring properties under the old binding name | After `function.bindings`, use the new name under `bindings` |
| `-in-1` exists but `-out-1` does not | Function has two inputs and one output | That may be the intended contract of a 2 → 1 function |
| `Flux<List<T>>` emits multiple items, mistaken for multiple outputs | Confusing item count with port count | Port count depends on arity, not item count |
| Added `Tuple3` and old sources swapped places | Inserted tuple element in the middle and forgot to update bindings | Review order of `getT1()`, `getT2()`, `getT3()` |
| Both inputs use `application/json` yet deserialization fails | Java type at the port is incompatible with the payload | Inspect the `Flux<T>` generic type of that exact input |

## 12. Self-check exercises

**Question 1.** A bean named `combine` has the signature:

~~~java
Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
~~~

How many bindings are there, and what are their default names?

**Answer:** Three bindings: `combine-in-0`, `combine-in-1`, and `combine-out-0`. Input 0 has `String` payloads; input 1 has `Long` payloads. There is only one output.

**Question 2.** A function `route` returns `Tuple3<Flux<A>, Flux<B>, Flux<C>>`. Which output does `getT3()` correspond to?

**Answer:** `route-out-2`, because binding indices start at 0 while `getTn()` starts at 1.

**Question 3.** After configuring:

~~~properties
spring.cloud.stream.function.bindings.route-out-1=failedOrders
spring.cloud.stream.bindings.failedOrders.destination=orders.failed
~~~

What binding name and destination will output index 1 of `route` use?

**Answer:** The binding name used for configuration is `failedOrders`; the destination is `orders.failed`. The index is still 1, corresponding to `getT2()` in the output tuple.

**Question 4.** If `destination` is not configured for `route-in-0`, what destination name does Spring Cloud Stream use by default?

**Answer:** The binding name `route-in-0`. That is why you should explicitly configure `destination` in applications with their own topic naming conventions.

**Question 5.** A `Function<Flux<Order>, Tuple2<Flux<Accepted>, Flux<Rejected>>>` emits 10,000 `Accepted` and 50 `Rejected` events. How many output bindings are there?

**Answer:** **Two**: `-out-0` and `-out-1`. The number of messages on each branch does not change the number of bindings.

## References

- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding and binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-names.html)
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Producing and consuming messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming model and Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Project Reactor — Tuple2 API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
